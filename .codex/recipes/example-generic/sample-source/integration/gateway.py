class PaymentGateway:
    def authorize(self, amount: int) -> bool:
        return amount > 0
