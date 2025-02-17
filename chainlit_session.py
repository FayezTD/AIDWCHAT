import asyncio
import json
import mimetypes
import shutil
import uuid
from typing import TYPE_CHECKING, Any, Callable, Deque, Dict, Literal, Optional, Union

import aiofiles

from chainlit.logger import logger
from chainlit.types import FileReference

if TYPE_CHECKING:
    from chainlit.types import FileDict
    from chainlit.user import PersistedUser, User

ClientType = Literal["webapp", "copilot", "teams", "slack", "discord"]

class JSONEncoderIgnoreNonSerializable(json.JSONEncoder):
    def default(self, o):
        try:
            return super().default(o)
        except TypeError:
            return None

def clean_metadata(metadata: Dict, max_size: int = 1048576):
    cleaned_metadata = json.loads(
        json.dumps(metadata, cls=JSONEncoderIgnoreNonSerializable, ensure_ascii=False)
    )

    metadata_size = len(json.dumps(cleaned_metadata).encode("utf-8"))
    if metadata_size > max_size:
        cleaned_metadata = {
            "message": f"Metadata size exceeds the limit of {max_size} bytes. Redacted."
        }

    return cleaned_metadata

class BaseSession:
    """Base object."""

    thread_id_to_resume: Optional[str] = None
    client_type: ClientType
    current_task: Optional[asyncio.Task] = None

    def __init__(
        self,
        id: str,
        client_type: ClientType,
        thread_id: Optional[str],
        user: Optional[Union["User", "PersistedUser"]],
        token: Optional[str],
        user_env: Optional[Dict[str, str]],
        chat_profile: Optional[str] = None,
        http_referer: Optional[str] = None,
        http_cookie: Optional[str] = None,
    ):
        if thread_id:
            self.thread_id_to_resume = thread_id
        self.thread_id = thread_id or str(uuid.uuid4())
        self.user = user
        self.client_type = client_type
        self.token = token
        self.has_first_interaction = False
        self.user_env = user_env or {}
        self.chat_profile = chat_profile
        self.http_referer = http_referer
        self.http_cookie = http_cookie

        self.files: Dict[str, FileDict] = {}

        self.id = id

        self.chat_settings: Dict[str, Any] = {}

    @property
    def files_dir(self):
        from chainlit.config import FILES_DIRECTORY

        return FILES_DIRECTORY / self.id

    async def persist_file(
        self,
        name: str,
        mime: str,
        path: Optional[str] = None,
        content: Optional[Union[bytes, str]] = None,
    ) -> FileReference:
        if not path and not content:
            raise ValueError(
                "Either path or content must be provided to persist a file"
            )

        self.files_dir.mkdir(exist_ok=True)

        file_id = str(uuid.uuid4())

        file_path = self.files_dir / file_id

        file_extension = mimetypes.guess_extension(mime)

        if file_extension:
            file_path = file_path.with_suffix(file_extension)

        if path:
            async with (
                aiofiles.open(path, "rb") as src,
                aiofiles.open(file_path, "wb") as dst,
            ):
                await dst.write(await src.read())
        elif content:
            async with aiofiles.open(file_path, "wb") as buffer:
                if isinstance(content, str):
                    content = content.encode("utf-8")
                await buffer.write(content)

        file_size = file_path.stat().st_size
        self.files[file_id] = {
            "id": file_id,
            "path": file_path,
            "name": name,
            "type": mime,
            "size": file_size,
        }

        return {"id": file_id}

    def to_persistable(self) -> Dict:
        from chainlit.user_session import user_sessions

        user_session = user_sessions.get(self.id) or {}
        user_session["chat_settings"] = self.chat_settings
        user_session["chat_profile"] = self.chat_profile
        user_session["http_referer"] = self.http_referer
        user_session["client_type"] = self.client_type
        metadata = clean_metadata(user_session)
        return metadata

class HTTPSession(BaseSession):
    """Internal HTTP session object. Used to consume Chainlit through API (no websocket)."""

    def __init__(
        self,
        id: str,
        client_type: ClientType,
        thread_id: Optional[str] = None,
        user: Optional[Union["User", "PersistedUser"]] = None,
        token: Optional[str] = None,
        user_env: Optional[Dict[str, str]] = None,
        http_referer: Optional[str] = None,
        http_cookie: Optional[str] = None,
    ):
        super().__init__(
            id=id,
            thread_id=thread_id,
            user=user,
            token=token,
            client_type=client_type,
            user_env=user_env,
            http_referer=http_referer,
            http_cookie=http_cookie,
        )

    def delete(self):
        if self.files_dir.is_dir():
            shutil.rmtree(self.files_dir)

ThreadQueue = Deque[tuple[Callable, object, tuple, Dict]]

class WebsocketSession(BaseSession):
    """Internal web socket session object."""

    to_clear: bool = False

    def __init__(
        self,
        id: str,
        socket_id: str,
        emit: Callable[[str, Any], None],
        emit_call: Callable[[Literal["ask", "call_fn"], Any, Optional[int]], Any],
        user_env: Dict[str, str],
        client_type: ClientType,
        thread_id: Optional[str] = None,
        user: Optional[Union["User", "PersistedUser"]] = None,
        token: Optional[str] = None,
        chat_profile: Optional[str] = None,
        languages: Optional[str] = None,
        http_referer: Optional[str] = None,
        http_cookie: Optional[str] = None,
    ):
        super().__init__(
            id=id,
            thread_id=thread_id,
            user=user,
            token=token,
            user_env=user_env,
            client_type=client_type,
            chat_profile=chat_profile,
            http_referer=http_referer,
            http_cookie=http_cookie,
        )

        self.socket_id = socket_id
        self.emit_call = emit_call
        self.emit = emit

        self.restored = False

        self.thread_queues: Dict[str, ThreadQueue] = {}

        ws_sessions_id[self.id] = self
        ws_sessions_sid[socket_id] = self

        self.languages = languages

    def restore(self, new_socket_id: str):
        ws_sessions_sid.pop(self.socket_id, None)
        ws_sessions_sid[new_socket_id] = self
        self.socket_id = new_socket_id
        self.restored = True

    def delete(self):
        if self.files_dir.is_dir():
            shutil.rmtree(self.files_dir)
        ws_sessions_sid.pop(self.socket_id, None)
        ws_sessions_id.pop(self.id, None)

    async def flush_method_queue(self):
        for method_name, queue in self.thread_queues.items():
            while queue:
                method, self, args, kwargs = queue.popleft()
                try:
                    await method(self, *args, **kwargs)
                except Exception as e:
                    logger.error(f"Error while flushing {method_name}: {e}")

    @classmethod
    def get(cls, socket_id: str):
        return ws_sessions_sid.get(socket_id)

    @classmethod
    def get_by_id(cls, session_id: str):
        return ws_sessions_id.get(session_id)

    @classmethod
    def require(cls, socket_id: str):
        if session := cls.get(socket_id):
            return session
        raise ValueError("Session not found")

ws_sessions_sid: Dict[str, WebsocketSession] = {}
ws_sessions_id: Dict[str, WebsocketSession] = {}