from aiogram.fsm.state import State, StatesGroup


class TaskSubmissionStates(StatesGroup):
    waiting_submission = State()
