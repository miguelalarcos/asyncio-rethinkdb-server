from rethinkdb import r
from sdp import get_connection

class SetError(Exception):
    pass

class ValidationError(Exception):
    pass

class PathError(Exception):
    pass

class DocNotFoundError(Exception):
    pass

public = lambda *args: True
never  = lambda *args: False
CURRENT_USER = object()

class Schema:
    reserved_kw = ['__get', '__set', '__set_document', '__get_document', \
                   '__create_document', '__ownership', '__set_default', \
                   '__get_default']

    def __init__(self, doc, user_id):
        self.doc = doc
        self.user_id = user_id

    def can_update(self, stored_user_id):
        return False

    async def update(self):
        connection = await get_connection()
        old_doc = await r.table(self.table).get(self.doc['id']).run(connection)
        if not old_doc:
            raise DocNotFoundError('document not found', self.table, self.doc['id'])
        if not self.can_update(old_doc['user_id']):
            raise SetError('can not update ' + self.table + ', id: ' + str(self.doc['id']))
        else:
            for key, value in self.doc.items():
                if key == 'id':
                    continue
                self._update(key, value)
            connection = await get_connection()
            id = self.doc.pop('id')
            await r.table(self.table).get(id).update(self.doc).run(connection)

    def _update(self, path, value):
        doc = self.doc
        schema = self.schema
        set_default = schema.get('__set_default', never)
        validation_default = public
        paths = path.split('.')
        last = paths[-1]

        for key in paths:
            if key.isdigit():
                key = int(key)
            else:
                try:
                    schema[key]
                except KeyError:
                    raise PathError('path does not exist in schema', key)
                validation = schema[key].get('validation', validation_default)
                if key == last:
                    schema = schema[key]['type']  
                    break
                set_ = schema[key].get('set', set_default)
                
                if not set_():
                    raise SetError('can not set')     
                schema = schema[key]['type']          
            
            if type(schema) is list:
                schema = schema[0]
                try:
                    doc = doc[key]
                except IndexError:
                    raise PathError('path does not exist in doc', key)
            
            if issubclass(schema, Schema) and key != last:                
                try:                
                    doc = doc[key]
                    schema = schema.schema
                except KeyError:
                    raise PathError('path does not exist in doc', key)

        if type(schema) is list:
            schema = schema[0]
            if issubclass(schema, Schema):
                if '$pull' in value:
                    doc[key] = [k for k in doc[key] if k != value['$pull']]
                else:
                    doc[key].append(schema(value).insert())
            else:
                if '$pull' in value:
                    doc[key] = [k for k in doc[key] if k != value['$pull']]
                else:
                    doc[key].append(value)
        elif issubclass(schema, Schema):
            schema = schema.schema
            set_default = schema.get('__set_default', never)
            keys = [k  for k in schema.keys() if k not in self.reserved_kw] 
            ret = {}
            for k in keys:
                try:
                    #schema[k]
                    value[k]
                    set_ = schema[k].get('set', set_default)
                except KeyError:
                    raise PathError('path does not exist', k)
                #except TypeError:
                #    raise PathError('type error path does not exist', k)
                
                if not set_(): 
                    raise SetError('can not set', k, value)    
                if not schema[k]['type'] == type(value[k]) or not schema[k].get('validation', public)(value[k]):
                    raise ValidationError('can not set (validation)', k, value)
                ret[k] = value[k]
                doc[key].update({k: value[k]})

        elif isinstance(value, schema) and validation(value):
            try:
                doc[key] = value
            except IndexError:
                raise PathError('path does not exist in doc', key)
        else:
            raise ValidationError('not valid', key, value)

    async def insert(self, document=None):
        if not document:
            document = self.doc
        schema = self.schema
        ret = {}
        set_document = set(document.keys())
        set_schema = set(schema.keys()) - set(self.reserved_kw)
        intersection =  set_document & set_schema 
        missing = set_schema - set_document
        if len(set_document - set_schema) > 0:
            raise Exception('keywords not in schema')

        for key in missing | intersection:            
            #if schema[key]['type'].__class__ == Schema:         
            if issubclass(schema[key]['type'], Schema):       
                if document.get(key):                    
                    ret[key] = schema[key]['type']().insert(document[key])
            elif type(schema[key]['type']) is list:
                if document.get(key):
                    ret[key] = [schema[key]['type'][0]().insert(k) for k in document[key]]
            elif 'computed' not in schema[key]:
                validation = schema[key].get('validation', public)
                required = schema[key].get('required', False)
                mtype = schema[key]['type']
                initial = schema[key].get('initial')
                if initial == CURRENT_USER:
                    initial = self.user_id
                else:
                    initial = initial and initial() 
                v = document.get(key, initial)
                
                if required and v is None:
                    raise ValidationError('required')

                if v is not None and (not isinstance(v, mtype) or not validation(v)):
                    raise ValidationError('not valid prop or missing', key)
                if key in intersection or initial is not None: 
                    ret[key] = document.get(key, initial)
            else:
                create = schema[key].get('computed')
                val = create(document) 
                ret[key] = val
        connection = await get_connection()
        result = await r.table(self.table).insert(ret).run(connection)
        print(result)