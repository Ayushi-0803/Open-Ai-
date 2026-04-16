from interface.routes import create_checkout_handler


def test_create_checkout_handler():
    handler = create_checkout_handler()
    assert handler.create_user("user_123").user_id == "user_123"
