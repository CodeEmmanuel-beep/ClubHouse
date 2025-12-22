from pydantic import BaseModel, ConfigDict, Field, computed_field
from typing import Optional, List, Generic, TypeVar
from datetime import datetime, timezone, date
from enum import Enum

T = TypeVar("T")


class UserResponse(BaseModel):
    profile_picture: str | None = None
    email: str
    username: str
    name: str
    age: int
    nationality: str
    phone_number: float | None = None
    address: str | None = None

    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    username: str
    password: str


class Chat(BaseModel):
    id: Optional[int] = None
    receiver: Optional[str]
    username: Optional[str]
    message: str | None = None
    pics: str | None = None
    delivered: bool = False
    seen: bool = False
    time_of_chat: Optional[datetime]
    conversation_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UserRes(BaseModel):
    profile_picture: str | None = None
    email: str
    username: str
    name: str
    nationality: str
    model_config = ConfigDict(from_attributes=True)


class TaskResponse(BaseModel):
    id: Optional[int] | None = None
    user_id: int | None = None
    target: Optional[str]
    amount_required_to_hit_target: float | None = None
    day_of_target: date
    monthly_income: float | None = None
    amount_saved: float | None = None
    complete: bool = False
    status: str | None = None
    time_of_initial_prep: datetime | None = None

    @computed_field
    def days_remaining(self) -> str:
        target = datetime.combine(
            self.day_of_target, datetime.min.time(), tzinfo=timezone.utc
        )
        remaining = target - datetime.now(timezone.utc)
        seconds = remaining.total_seconds()
        if seconds <= 0:
            return "Time up"
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 86400 % 3600) // 60)
        if days > 1:
            return f"'{days}' days,'{hours}' hrs, '{minutes}' mins"
        elif hours > 1:
            return f"'{hours}' hrs, '{minutes}' mins"
        else:
            return f"'{minutes}' mins"

    @computed_field
    def daily_required_savings(self) -> str:
        if self.amount_required_to_hit_target > 0:
            remaining = datetime.combine(
                self.day_of_target, datetime.min.time(), tzinfo=timezone.utc
            )
            value = remaining - datetime.now(timezone.utc)
            seconds = value.total_seconds()
            if seconds:
                check = max(int(seconds // 86400), 0)
            if seconds <= 0:
                return "past"
            if check <= 0:
                return "match your previous savings"
            left = self.monthly_income - self.amount_required_to_hit_target
            overflow = self.amount_saved - self.amount_required_to_hit_target
            data = (self.amount_required_to_hit_target - self.amount_saved) / check
            if check <= 31:
                if self.amount_saved == self.amount_required_to_hit_target:
                    return "target amount acquired"
                elif self.amount_saved > self.amount_required_to_hit_target:
                    return {
                        f"target overflow: amount saved exceeds amount required by: '{overflow}'"
                    }
                else:
                    return (
                        f"amount to save daily: '{data}', total amount left after savings: '{left}'",
                    )

            daily = (self.monthly_income * 12) / 365
            target_amount = self.amount_required_to_hit_target / check
            mata = (self.amount_required_to_hit_target - self.amount_saved) / check
            left1 = daily - target_amount
            if check > 31:
                if self.amount_saved == self.amount_required_to_hit_target:
                    return "target amount acquired"
                elif self.amount_saved > self.amount_required_to_hit_target:
                    return f"target overflow, you have saved '{overflow}' in excess"
                else:
                    return f"amount to save daily: '{mata}',total amount left to spend after savings: '{left1}'"
        else:
            return "no finances required"

    model_config = ConfigDict(from_attributes=True)


class TaskT(BaseModel):
    group_id: int
    task_id: int | None = None
    new_target: str | None = None
    new_day_of_target: date | None = None
    new_amount_required: float | None = None
    new_monthly_income: float | None = None


class Piggy(BaseModel):
    group_id: int | None = None
    task_id: int
    amount_saved_for_the_day: int


class ContributeResponse(BaseModel):
    target: str
    contribution: float
    total: List[float] = Field(default_factory=list)
    time: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class BrokeResponse(BaseModel):
    monthly_income: float
    amount_required: float
    day_of_target: date


class ContributeResponseG(BaseModel):
    name: str
    contribution: float
    time: Optional[datetime]
    member_total: List[float] = Field(default_factory=list)
    group_total: List[float] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class Participants(BaseModel):
    group_id: int
    grouptask_id: int
    username: str
    assignment: str
    amount_levied: float | None = None

    model_config = ConfigDict(from_attributes=True)


class ParticipantResponse(BaseModel):
    id: Optional[int] = None
    username: str
    assignment: str
    assignment_complete: bool = False
    amount_levied: float | None = None
    paid: bool = False
    time_of_assignment: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class OpinionRes(BaseModel):
    content: str
    group_id: int
    task_id: int

    model_config = ConfigDict(from_attributes=True)


class Voting(BaseModel):
    upvote: int = 0
    downvote: int = 0


class OpinionResponse(BaseModel):
    id: int | None = None
    profile_picture: List[str] = Field(default_factory=list)
    username: List[str] = Field(default_factory=list)
    content: str
    vote_count: int
    votes: List[Voting] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TaskRes(BaseModel):
    group_id: int | None = None
    target: Optional[str]
    amount_required_to_hit_target: float | None = None
    day_of_target: date
    monthly_income: float | None = None
    amount_saved: float | None = None


class TaskResponseG(BaseModel):
    id: Optional[int] | None = None
    user_id: int | None = None
    group_id: int | None = None
    target: Optional[str]
    amount_required_to_hit_target: float | None = None
    day_of_target: date
    monthly_income: float | None = None
    amount_saved: float | None = None
    complete: bool = False
    status: str | None = None
    edited: bool = False
    opinion_count: int | None = None
    opinions: List[OpinionResponse] = Field(default_factory=list)
    participants: List[ParticipantResponse] = Field(default_factory=list)
    time_of_initial_prep: datetime | None = None

    @computed_field
    def days_remaining(self) -> str:
        target = datetime.combine(
            self.day_of_target, datetime.min.time(), tzinfo=timezone.utc
        )
        remaining = target - datetime.now(timezone.utc)
        seconds = remaining.total_seconds()
        if seconds <= 0:
            return "Time up"
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 86400 % 3600) // 60)
        if days > 1:
            return f"'{days}' days,'{hours}' hrs, '{minutes}' mins"
        elif hours > 1:
            return f"'{hours}' hrs, '{minutes}' mins"
        else:
            return f"'{minutes}' mins"

    @computed_field
    def daily_required_savings(self) -> str:
        if self.amount_required_to_hit_target > 0:
            remaining = datetime.combine(
                self.day_of_target, datetime.min.time(), tzinfo=timezone.utc
            )
            value = remaining - datetime.now(timezone.utc)
            seconds = value.total_seconds()
            if seconds:
                check = max(int(seconds // 86400), 0)
            if seconds <= 0:
                return "past"
            if check <= 0:
                return "match your previous savings"
            left = self.monthly_income - self.amount_required_to_hit_target
            overflow = self.amount_saved - self.amount_required_to_hit_target
            data = (self.amount_required_to_hit_target - self.amount_saved) / check
            if check <= 31:
                if self.amount_saved == self.amount_required_to_hit_target:
                    return "target amount acquired"
                elif self.amount_saved > self.amount_required_to_hit_target:
                    return {
                        f"target overflow: amount saved exceeds amount required by: '{overflow}'"
                    }
                else:
                    return (
                        f"amount to save daily: '{data}', total amount left after savings: '{left}'",
                    )

            daily = (self.monthly_income * 12) / 365
            target_amount = self.amount_required_to_hit_target / check
            mata = (self.amount_required_to_hit_target - self.amount_saved) / check
            left1 = daily - target_amount
            if check > 31:
                if self.amount_saved == self.amount_required_to_hit_target:
                    return "target amount acquired"
                elif self.amount_saved > self.amount_required_to_hit_target:
                    return f"target overflow, you have saved '{overflow}' in excess"
                else:
                    return f"amount to save daily: '{mata}',total amount left to spend after savings: '{left1}'"
        else:
            return "this is a target without financial requirements"

    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel):
    page: int
    limit: int
    total: int


class PaginatedMetadata(BaseModel, Generic[T]):
    items: List[T]
    pagination: PaginatedResponse


class StandardResponse(BaseModel, Generic[T]):
    status: str
    message: str
    data: Optional[T] = None


class ReactionsSummary(BaseModel):
    like: int = 0
    love: int = 0
    haha: int = 0
    wow: int = 0
    sad: int = 0
    angry: int = 0


class CommentResponse(BaseModel):
    blog_id: int | None = None
    content: str = Field(..., max_length=180)

    model_config = ConfigDict(from_attributes=True)


class Commenter(BaseModel):
    id: Optional[int] = None
    profile_picture: List[str] = Field(default_factory=list)
    name: List[str] = Field(default_factory=list)
    blog_id: int | None = None
    content: str = Field(..., max_length=180)
    reacts_count: int | None = None
    reactions: List[ReactionsSummary] = Field(default_factory=list)
    time_of_post: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class Blogger(BaseModel):
    id: Optional[int] = None
    profile_picture: List[str] = Field(default_factory=list)
    name: List[str] = Field(default_factory=list)
    image: str | None = None
    target: str | None = Field(None, max_length=300)
    details: str | None = None
    reactions: List[ReactionsSummary] = Field(default_factory=list)
    reacts_count: int | None = None
    comments_count: int | None = None
    share_count: int | None = None
    comments: List[Commenter] = Field(default_factory=list)
    time_of_post: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class Sharing(Enum):
    love = "love"
    angry = "angry"
    laugh = "laugh"
    wow = "wow"
    sad = "sad"


class Sharer(BaseModel):
    id: Optional[int] = None
    profile_picture: List[str] = Field(default_factory=list)
    name: List[str] = Field(default_factory=list)
    blog_id: int
    type: Optional[Sharing] = None
    content: Optional[str] = None
    blog: Blogger = Field(default_factory=list)
    time_of_share: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class MemberResponse(BaseModel):
    member_profile_picture: List[str] = Field(default_factory=list)
    username: str

    model_config = ConfigDict(from_attributes=True)


class GroupResponse(BaseModel):
    id: int
    profile_picture: str | None = None
    name: str

    model_config = ConfigDict(from_attributes=True)
