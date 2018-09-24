import asyncio
import websockets
from sdp import sdp, method, sub
from schema import Schema, public, never, CURRENT_USER
from rethinkdb import r

r.set_loop_type("asyncio")

class XSchema(Schema):
    table = 'test'
    schema = {
        "__set_default": public,
        'x': {
            'type': int,
            'validation': lambda v: v > -100
        },
        'user_id': {
            'type': str,
            'initial': CURRENT_USER,
            'set': never
        }
    }  

    def can_insert(self):
        return self.user_id is not None

    def can_update(self, stored_user_id):
        return stored_user_id == self.user_id

@method
async def add(user_id, a, b):
    return a + b

@method
async def create_X(user_id, x):
    doc = XSchema(doc={'x': x}, user_id=user_id)
    await doc.insert()

@method 
async def set_x(user_id, id, value):
    doc = XSchema(doc={'id': id, 'x': value}, user_id=user_id)
    await doc.update()

@sub
def x_less_than(user_id, max):
    print(user_id, max)
    return r.table('test').filter(lambda row: (row['x'] < max) & (row['user_id'] == user_id))

def main():
    start_server = websockets.serve(sdp, 'localhost', 8888)

    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()