from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_full_name = State()
    waiting_phone = State()
    waiting_city = State()
    waiting_pdn_consent = State()
