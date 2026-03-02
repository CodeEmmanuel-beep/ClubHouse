from pydantic import BaseModel, ConfigDict, Field, computed_field
from typing import Optional, List, Generic, TypeVar
from datetime import datetime, timezone, date
from enum import Enum

T = TypeVar("T")


class UserResponse(BaseModel):
    id: int
    profile_picture: str | None = None
    email: str
    username: str
    name: str
    age: int
    nationality: str | None = None
    phone_number: float | None = None
    address: str | None = None

    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    username: str
    password: str


class Chat(BaseModel):
    id: Optional[int]
    name: str = Field(default_factory=str)
    message: str | None = None
    pics: list[str] | str | None = None
    delivered: bool = Field(default=False)
    seen: bool = Field(default=False)
    time_of_chat: Optional[datetime]
    conversation_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UserRes(BaseModel):
    id: int
    profile_picture: str | None = None
    email: str
    username: str
    name: str
    nationality: str | None = None
    model_config = ConfigDict(from_attributes=True)


class TaskResponse(BaseModel):
    id: Optional[int] | None = None
    target: Optional[str]
    amount_required_to_hit_target: float = Field(default=0)
    day_of_target: date
    monthly_income: float = Field(default=0)
    amount_saved: float = Field(default=0)
    complete: bool = Field(default=False)
    status: str = Field(default="pending")
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
    def daily_required_savings(self) -> str | dict | None:
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
                        "target overflow": f"amount saved exceeds amount required by '{overflow}'"
                    }
                else:
                    return {
                        "amount to save daily": f"{data}",
                        "total amount left after savings": f"{left}",
                    }

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
    assignment_complete: bool = Field(default=False)
    amount_levied: float | None = None
    paid: bool = Field(default=False)
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
    group_id: int
    task_id: int
    profile_picture: str | None = Field(default_factory=str)
    username: List[str] = Field(default_factory=list)
    content: str
    vote_count: int = Field(default=0)
    votes: Voting | None = Field(default_factory=Voting)

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
    name: str = Field(default_factory=str)
    edited: bool = Field(default=False)
    target: Optional[str]
    amount_required_to_hit_target: float = Field(default=0)
    day_of_target: date
    monthly_income: float = Field(default=0)
    amount_saved: float = Field(default=0)
    complete: bool = Field(default=False)
    status: str = Field(default="pending")
    time_of_initial_prep: datetime | None = None
    opinion_count: int = Field(default=0)
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
    def daily_required_savings(self) -> str | dict | None:
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
                        "target overflow": f"amount saved exceeds amount required by: '{overflow}'"
                    }
                else:
                    return {
                        "amount to save daily": f"{data}",
                        "total amount left after savings": f"{left}",
                    }

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
    laugh: int = 0
    wow: int = 0
    sad: int = 0
    angry: int = 0


class Commenter(BaseModel):
    blog_id: int | None = None
    content: str = Field(..., max_length=180)

    model_config = ConfigDict(from_attributes=True)


class CommentResponse(BaseModel):
    id: Optional[int] = None
    profile_picture: str | None = Field(default_factory=str)
    name: str = Field(default_factory=str)
    blog_id: int | None = None
    content: str = Field(..., max_length=180)
    reacts_count: int = Field(default=0)
    reactions: ReactionsSummary | None = Field(default_factory=ReactionsSummary)
    time_of_post: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class Blogger(BaseModel):
    id: Optional[int] = None
    profile_picture: str | None = Field(default_factory=str)
    name: str = Field(default_factory=str)
    image: list[str] | dict | str | None = None
    target: str | None = Field(None, max_length=300)
    details: str | None = None
    reacts_count: int = Field(default=0)
    reactions: ReactionsSummary = Field(default_factory=ReactionsSummary)
    comments_count: int = Field(default=0)
    share_count: int = Field(default=0)
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
    profile_picture: str | None = Field(default_factory=str)
    name: str = Field(default_factory=str)
    blog_id: int | None = None
    type: Optional[Sharing] = None
    content: Optional[str] = None
    time_of_share: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MemberResponse(BaseModel):
    member_profile_picture: str | None = Field(default_factory=str)
    username: str

    model_config = ConfigDict(from_attributes=True)


class GroupResponse(BaseModel):
    id: int
    profile_picture: str | None = None
    name: str

    model_config = ConfigDict(from_attributes=True)
