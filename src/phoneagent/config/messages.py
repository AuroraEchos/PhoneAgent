"""English UI/runtime messages for PhoneAgent."""

MESSAGES = {
    "thinking": "Thinking",
    "action": "Action",
    "task_completed": "Task Completed",
    "done": "Done",
    "starting_task": "Starting task",
    "final_result": "Final Result",
    "task_result": "Task Result",
    "confirmation_required": "Confirmation Required",
    "continue_prompt": "Continue? (y/n)",
    "manual_operation_required": "Manual Operation Required",
    "manual_operation_hint": "Please complete the operation manually...",
    "press_enter_when_done": "Press Enter when done",
    "connection_failed": "Connection Failed",
    "connection_successful": "Connection Successful",
    "step": "Step",
    "task": "Task",
    "result": "Result",
    "performance_metrics": "Performance Metrics",
    "time_to_first_token": "Time to First Token (TTFT)",
    "time_to_thinking_end": "Time to Thinking End",
    "total_inference_time": "Total Inference Time",
}


def get_messages() -> dict[str, str]:
    """Get all UI messages."""
    return MESSAGES


def get_message(key: str) -> str:
    """Get one UI message by key."""
    return MESSAGES.get(key, key)
