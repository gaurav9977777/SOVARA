import os
import aiofiles
from chainlit.data.storage_clients.base import BaseStorageClient

class LocalStorageClient(BaseStorageClient):
    def __init__(self, base_dir="public/files"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    async def upload_file(self, object_key: str, data: bytes | str, mime: str = "application/octet-stream", overwrite: bool = True, content_disposition: str | None = None) -> dict:
        file_path = os.path.join(self.base_dir, object_key)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        mode = "wb" if isinstance(data, bytes) else "w"
        async with aiofiles.open(file_path, mode) as f:
            await f.write(data)
        
        return {"object_key": object_key, "url": f"/{self.base_dir}/{object_key}"}

    async def delete_file(self, object_key: str) -> bool:
        file_path = os.path.join(self.base_dir, object_key)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False

    async def get_read_url(self, object_key: str) -> str:
        return f"/{self.base_dir}/{object_key}"

    async def close(self) -> None:
        pass
