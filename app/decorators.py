from functools import wraps
from inspect import signature

from flask import jsonify, request

def query_params():
    def snake_to_camel(word):
        words = word.split('_')
        return words[0] + ''.join(x.capitalize() for x in words[1:])

    def decorator(f):
        parameters = signature(f).parameters

        @wraps(f)
        def wrapped(*args, **kwargs):
            payload = request.get_json(silent=True)
            params = {name: payload.get(snake_to_camel(name), param.default) for name, param in parameters.items()}

            if not all(v is not None for v in params.values()):
                return jsonify({"error": "You are missing a required field."}), 400

            return f(**params)

        return wrapped

    return decorator
