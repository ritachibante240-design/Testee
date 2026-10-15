from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VideoBase(BaseModel):
    title: str
    description: str | None = None
    category: str
    views: int = 0
    duration: int = 0
    video_url: str
    thumbnail_url: str | None = None


class VideoCreate(VideoBase):
    pass


class VideoResponse(VideoBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)