from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    DateTime,
    String,
    Float,
    ForeignKey,
    UniqueConstraint,
    Enum as SQLEnum,
    Date,
    Table,
    Text,
)
from enum import Enum
from app.core.declarative import Base
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime, timezone


def current_utc_time():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String)
    username = Column(String)
    password = Column(String)
    name = Column(String)
    is_active = Column(Boolean, default=True)
    age = Column(Integer)
    nationality = Column(String)
    phone_number = Column(Float)
    address = Column(String)
    profile_picture = Column(String, nullable=True)

    tasks = relationship("Task", back_populates="user")
    group_tasks = relationship("GroupTask", back_populates="user")
    blogs = relationship("Blog", back_populates="user")
    comments = relationship("Comment", back_populates="user")
    reacts = relationship("React", back_populates="user")
    shares = relationship("Share", back_populates="user")
    messages = relationship("Messaging", back_populates="user")
    contributions = relationship("Contribute", back_populates="user")
    group_admins = relationship("GroupAdmin", back_populates="user")
    members = relationship("Member", back_populates="user")
    opinions = relationship("Opinion", back_populates="user")
    opinion_votes = relationship("OpinionVote", back_populates="user")


class Messaging(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    receiver = Column(Integer)
    message: Mapped[str] = mapped_column(String, nullable=True)
    pics: Mapped[str] = mapped_column(String, nullable=True)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    seen: Mapped[bool] = mapped_column(Boolean, default=False)
    sender_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    receiver_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    time_of_chat = Column(DateTime(timezone=True), default=current_utc_time, index=True)
    user = relationship("User", back_populates="messages")


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    target = Column(String)
    amount_required_to_hit_target = Column(Float, default=0)
    day_of_target = Column(Date)
    monthly_income = Column(Float, default=0)
    amount_saved = Column(Float, default=0)
    complete = Column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    time_of_initial_prep = Column(DateTime(timezone=True), default=current_utc_time)

    user = relationship("User", back_populates="tasks")


group_task_participants = Table(
    "group_task_participants",
    Base.metadata,
    Column(
        "group_task_id",
        ForeignKey("group_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "participant_id",
        ForeignKey("participants.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

members_participants = Table(
    "members_participants",
    Base.metadata,
    Column(
        "members_id", ForeignKey("members.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "participants_id",
        ForeignKey("participants.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class GroupTask(Base):
    __tablename__ = "group_tasks"
    id = Column(Integer, primary_key=True, index=True)
    edited = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    target = Column(String)
    amount_required_to_hit_target = Column(Float, default=0)
    day_of_target = Column(Date)
    monthly_income = Column(Float, default=0)
    amount_saved = Column(Float, default=0)
    complete = Column(Boolean, default=False)
    status = Column(String, default="pending")
    opinion_count = Column(Integer, default=0)
    time_of_initial_prep = Column(DateTime(timezone=True), default=current_utc_time)

    user = relationship("User", back_populates="group_tasks")
    group = relationship("Group", back_populates="group_tasks")
    contributions = relationship(
        "Contribute", back_populates="task", cascade="all, delete-orphan"
    )
    opinion_votes = relationship(
        "OpinionVote", back_populates="grouptask", cascade="all, delete-orphan"
    )
    opinions = relationship(
        "Opinion", back_populates="task", cascade="all, delete-orphan"
    )
    participants = relationship(
        "Participant",
        secondary=group_task_participants,
        back_populates="group_tasks",
        passive_deletes=True,
    )


class Participant(Base):
    __tablename__ = "participants"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    username = Column(String)
    assignment = Column(String)
    assignment_complete = Column(Boolean, default=False)
    amount_levied = Column(Float, default=0)
    paid = Column(Boolean, default=False)
    time_of_assignment = Column(
        DateTime(timezone=True), default=current_utc_time, index=True
    )

    group = relationship("Group", back_populates="participants")
    group_tasks = relationship(
        "GroupTask",
        secondary=group_task_participants,
        back_populates="participants",
        passive_deletes=True,
    )
    members = relationship(
        "Member",
        secondary=members_participants,
        back_populates="participants",
        passive_deletes=True,
    )


class GroupAdmin(Base):
    __tablename__ = "group_admins"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    group_id = Column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role = Column(String, default="admin")

    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="unique_group_admin"),
    )

    user = relationship("User", back_populates="group_admins")
    group = relationship("Group", back_populates="admins")


class Member(Base):
    __tablename__ = "members"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    group_id = Column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="unique_member_constraint"),
    )

    user = relationship("User", back_populates="members")
    group = relationship("Group", back_populates="members")
    participants = relationship(
        "Participant",
        secondary=members_participants,
        back_populates="members",
        passive_deletes=True,
    )


class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    profile_picture = Column(String, nullable=True)
    name = Column(String)

    contributions = relationship(
        "Contribute", back_populates="group", cascade="all, delete-orphan"
    )
    participants = relationship(
        "Participant", back_populates="group", cascade="all, delete-orphan"
    )
    admins = relationship(
        "GroupAdmin", back_populates="group", cascade="all, delete-orphan"
    )
    opinion_votes = relationship(
        "OpinionVote", back_populates="group", cascade="all, delete-orphan"
    )
    members = relationship(
        "Member", back_populates="group", cascade="all, delete-orphan"
    )
    group_tasks = relationship(
        "GroupTask", back_populates="group", cascade="all, delete-orphan"
    )
    opinions = relationship(
        "Opinion", back_populates="group", cascade="all, delete-orphan"
    )


class Contribute(Base):
    __tablename__ = "contributions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    grouptask_id = Column(
        Integer, ForeignKey("group_tasks.id", ondelete="CASCADE"), index=True
    )
    target = Column(String, nullable=True)
    name = Column(String, nullable=True)
    contribution = Column(Float)
    time = Column(DateTime(timezone=True), default=current_utc_time, index=True)

    user = relationship("User", back_populates="contributions")
    group = relationship("Group", back_populates="contributions")
    task = relationship("GroupTask", back_populates="contributions")


class Blog(Base):
    __tablename__ = "blogs"
    id = Column(Integer, primary_key=True, index=True)
    image = Column(String)
    target = Column(String)
    details = Column(Text)
    comments_count = Column(Integer, default=0)
    reacts_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    time_of_post = Column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), index=True
    )

    comments = relationship(
        "Comment", back_populates="blog", cascade="all, delete-orphan"
    )
    user = relationship("User", back_populates="blogs")
    shares = relationship("Share", back_populates="blog")
    react = relationship("React", back_populates="blog", cascade="all, delete-orphan")


class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String)
    blog_id = Column(Integer, ForeignKey("blogs.id", ondelete="CASCADE"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    reacts_count = Column(Integer, default=0)
    time_of_post = Column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), index=True
    )

    blog = relationship("Blog", back_populates="comments")
    user = relationship("User", back_populates="comments")
    react = relationship(
        "React", back_populates="comment", cascade="all, delete-orphan"
    )


class Opinion(Base):
    __tablename__ = "opinions"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    task_id = Column(
        Integer, ForeignKey("group_tasks.id", ondelete="CASCADE"), index=True
    )
    vote_count = Column(Integer, default=0)

    task = relationship("GroupTask", back_populates="opinions")
    user = relationship("User", back_populates="opinions")
    group = relationship("Group", back_populates="opinions")
    opinion_votes = relationship(
        "OpinionVote", back_populates="opinion", cascade="all, delete-orphan"
    )


class OpinionEnum(str, Enum):
    upvote = "upvote"
    downvote = "downvote"


class OpinionVote(Base):
    __tablename__ = "opinion_votes"

    id = Column(Integer, primary_key=True, index=True)
    opinion_id = Column(
        Integer, ForeignKey("opinions.id", ondelete="CASCADE"), nullable=False
    )
    group_id = Column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    grouptask_id = Column(
        Integer, ForeignKey("group_tasks.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    vote = Column(SQLEnum(OpinionEnum), nullable=False)

    __table_args__ = (
        UniqueConstraint("opinion_id", "user_id", name="unique_user_vote"),
    )
    user = relationship("User", back_populates="opinion_votes")
    opinion = relationship("Opinion", back_populates="opinion_votes")
    group = relationship("Group", back_populates="opinion_votes")
    grouptask = relationship("GroupTask", back_populates="opinion_votes")


class ReactionType(str, Enum):
    like = "like"
    love = "love"
    wow = "wow"
    laugh = "laugh"
    sad = "sad"
    angry = "angry"


class React(Base):
    __tablename__ = "reacts"
    id = Column(Integer, primary_key=True, index=True)
    type = Column(SQLEnum(ReactionType), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    comment_id = Column(
        Integer,
        ForeignKey("comments.id", ondelete="CASCADE"),
    )
    blog_id = Column(
        Integer,
        ForeignKey("blogs.id", ondelete="CASCADE"),
    )
    time_of_reaction = Column(
        DateTime(timezone=True), default=current_utc_time, index=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "comment_id", name="unique_comment_react"),
    )
    __table_args__ = (UniqueConstraint("user_id", "blog_id", name="unique_blog_react"),)
    comment = relationship("Comment", back_populates="react")
    blog = relationship("Blog", back_populates="react")
    user = relationship("User", back_populates="reacts")


class ShareType(str, Enum):
    love = "love"
    angry = "angry"
    laugh = "laugh"
    wow = "wow"
    sad = "sad"


class Share(Base):
    __tablename__ = "shares"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    blog_id = Column(Integer, ForeignKey("blogs.id", ondelete="SET NULL"), index=True)
    content = Column(String)
    type = Column(SQLEnum(ShareType), nullable=True)
    time_of_share = Column(
        DateTime(timezone=True), default=current_utc_time, index=True
    )

    user = relationship("User", back_populates="shares")
    blog = relationship("Blog", back_populates="shares")
