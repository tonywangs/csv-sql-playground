import json, sys
try:
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (384*1024*1024, 384*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
except (ImportError, ValueError):
    pass
from desk.core import encode, execute, inspect
request = json.load(sys.stdin)
try:
    result = inspect(request['path']) if request.get('inspect') else execute(request['path'], request)
    sys.stdout.buffer.write(encode({'ok':result}))
except Exception as exc:
    sys.stdout.buffer.write(encode({'error':str(exc)}))
