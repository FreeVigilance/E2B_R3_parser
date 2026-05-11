def quantity(k):
    def quantity_getter(obj):
        return obj.__dict__[k]
    
    def quantity_setter(obj, value):
        if value < 0:
            raise ValueError("Quantity cannot be negative")
        obj.__dict__[k] = value

    return property(quantity_getter, quantity_setter)

class MyClass:

    price = quantity('price')
    amount = quantity('amount')

    def __init__(self, price, amount):
        self.price = price
        self.amount = amount
    
