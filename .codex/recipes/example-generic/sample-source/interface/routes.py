from core.services import CheckoutService
from integration.gateway import PaymentGateway


def create_checkout_handler():
    return CheckoutService(PaymentGateway())
