from aiogram.fsm.state import State, StatesGroup


class VideoStates(StatesGroup):
    waiting_video = State()
