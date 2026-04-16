from core.models import User
from integration.gateway import PaymentGateway


class CheckoutService:
    def __init__(self, gateway: PaymentGateway):
        self.gateway = gateway

    def create_user(self, user_id: str) -> User:
        return User(user_id)
