"""Conversation domain exceptions mapped to safe HTTP responses."""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class ConversationNotFoundError(AppError):
    def __init__(self, message: str = "Conversation not found") -> None:
        super().__init__(
            code="conversation_not_found",
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ConversationArchivedError(AppError):
    def __init__(
        self,
        message: str = "Conversation is archived and cannot accept new messages",
    ) -> None:
        super().__init__(
            code="conversation_archived",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


class InvalidConversationTitleError(AppError):
    def __init__(self, message: str = "Invalid conversation title") -> None:
        super().__init__(
            code="invalid_conversation_title",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class MessageNotFoundError(AppError):
    def __init__(self, message: str = "Message not found") -> None:
        super().__init__(
            code="message_not_found",
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class MessageEditNotAllowedError(AppError):
    def __init__(self, message: str = "Only the latest user message can be edited") -> None:
        super().__init__(
            code="message_edit_not_allowed",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class MessageRegenerationNotAllowedError(AppError):
    def __init__(self, message: str = "Message regeneration is not allowed") -> None:
        super().__init__(
            code="message_regeneration_not_allowed",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class ConversationContextLimitError(AppError):
    def __init__(self, message: str = "Conversation context exceeds configured limits") -> None:
        super().__init__(
            code="conversation_context_limit",
            message=message,
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )


class ConversationGenerationError(AppError):
    def __init__(self, message: str = "Conversation generation failed") -> None:
        super().__init__(
            code="conversation_generation_error",
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


class ConversationStreamError(AppError):
    def __init__(self, message: str = "Conversation streaming failed") -> None:
        super().__init__(
            code="conversation_stream_error",
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


class SummaryGenerationError(AppError):
    def __init__(self, message: str = "Conversation summary generation failed") -> None:
        super().__init__(
            code="summary_generation_error",
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


class TitleGenerationError(AppError):
    def __init__(self, message: str = "Conversation title generation failed") -> None:
        super().__init__(
            code="title_generation_error",
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


class MessageTooLargeError(AppError):
    def __init__(self, message: str = "Message exceeds the maximum allowed length") -> None:
        super().__init__(
            code="message_too_large",
            message=message,
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )


class DuplicateClientRequestError(AppError):
    def __init__(self, message: str = "Duplicate client request") -> None:
        super().__init__(
            code="duplicate_client_request",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


class GeneralChatDisabledError(AppError):
    def __init__(self, message: str = "General chat without documents is disabled") -> None:
        super().__init__(
            code="general_chat_disabled",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class ConversationConflictError(AppError):
    def __init__(self, message: str = "Conversation is busy with another generation") -> None:
        super().__init__(
            code="conversation_conflict",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )
