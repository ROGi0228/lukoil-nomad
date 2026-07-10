from aiogram.fsm.state import State, StatesGroup


class DocumentStates(StatesGroup):
    waiting_photo = State()
