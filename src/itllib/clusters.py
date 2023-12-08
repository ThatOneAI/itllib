from contextlib import asynccontextmanager
import aiohttp
import json
from urllib.parse import urlparse


def create_patch(old_spec, new_spec):
    if new_spec == None:
        return None

    if old_spec == None:
        return new_spec

    patch = {}
    for k, v in new_spec.items():
        if k not in old_spec:
            patch[k] = v
            continue

        if type(v) == list:
            if not all([x == y for x, y in zip(v, old_spec[k])]):
                patch[k] = v
            continue

        if type(v) == dict:
            inner_patch = create_patch(old_spec[k], v)
            if len(inner_patch) > 0:
                patch[k] = inner_patch
            continue

        if v != old_spec[k]:
            patch[k] = v
            continue

    return patch


def merge(old_spec, patch):
    if old_spec == None:
        return patch

    new_spec = old_spec.copy()
    for k, v in patch.items():
        if type(v) == dict:
            new_spec[k] = merge(old_spec[k], v)
        else:
            new_spec[k] = v
    return new_spec


class DatabaseOperations:
    def __init__(self, secret):
        self.name = secret["spec"]["databaseName"]
        self.endpoint_url = secret["spec"]["secretBasicAuth"]["endpoint"]
        self.username = secret["spec"]["secretBasicAuth"]["username"]
        self.password = secret["spec"]["secretBasicAuth"]["password"]
        self.notifier = secret["spec"]["notifier"]


def _remove_scheme(url):
    parsed = urlparse(url)
    if parsed.scheme:
        # Remove the scheme and leading // from the URL
        return parsed._replace(scheme="").geturl()[2:]
    else:
        return url


class ClusterOperations:
    def __init__(self, database, stream, stream_obj, prefix=None):
        self.database = database
        self.stream = stream
        self.stream_obj = stream_obj
        self.prefix = prefix or ""

    async def create(self):
        params = {
            "domain": _remove_scheme(self.database.endpoint_url),
            "downstream": self.stream_obj.send_url,
        }
        params["prefix"] = self.prefix

        route_url = self.database.notifier + f"/clusters/routes/{self.database.name}"
        async with aiohttp.ClientSession() as session:
            async with session.post(route_url, params=params) as response:
                return response.status

    async def destroy(self):
        params = {
            "domain": _remove_scheme(self.database.endpoint_url),
            "downstream": self.stream_obj.send_url,
        }
        params["prefix"] = self.prefix

        route_url = self.database.notifier + f"/clusters/routes/{self.database.name}"
        async with aiohttp.ClientSession() as session:
            async with session.delete(route_url, params=params) as response:
                return response.status

    async def create_resource(self, config):
        name = config["metadata"]["name"]
        if not name.startswith(self.prefix):
            raise ValueError(f"Name {name} needs to start with prefix {self.prefix}")

        group, version = config["apiVersion"].split("/")
        kind = config["kind"]
        url = f"{self.database.endpoint_url}/{self.database.name}/resources/{group}/{version}/{kind}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=config) as response:
                return await response.json()

    async def read_all_resources(self, group, version, kind, name, utctime):
        if name and not name.startswith(self.prefix):
            raise ValueError(f"Name {name} needs to start with prefix {self.prefix}")

        url = f"{self.database.endpoint_url}/{self.database.name}/resources"
        params = {}
        if group:
            params["group"] = group
        if version:
            params["version"] = version
        if kind:
            params["kind"] = kind
        if name:
            params["name"] = name
        params["prefix"] = self.prefix
        if utctime:
            params["utctime"] = utctime

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                return await response.json()

    async def read_resource(self, group, version, kind, name):
        if not name.startswith(self.prefix):
            raise ValueError(f"Name {name} needs to start with prefix {self.prefix}")

        url = f"{self.database.endpoint_url}/{self.database.name}/resources/{group}/{version}/{kind}/{name}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.json()

    async def patch_resource(self, config):
        name = config["metadata"]["name"]
        if not name.startswith(self.prefix):
            raise ValueError(f"Name {name} needs to start with prefix {self.prefix}")

        group, version = config["apiVersion"].split("/")
        kind = config["kind"]
        url = f"{self.database.endpoint_url}/{self.database.name}/resources/{group}/{version}/{kind}/{name}"
        async with aiohttp.ClientSession() as session:
            async with session.patch(url, json=config) as response:
                return await response.read()

    async def update_resource(self, config):
        name = config["metadata"]["name"]
        if not name.startswith(self.prefix):
            raise ValueError(f"Name {name} needs to start with prefix {self.prefix}")

        group, version = config["apiVersion"].split("/")
        kind = config["kind"]
        url = f"{self.database.endpoint_url}/{self.database.name}/resources/{group}/{version}/{kind}/{name}?create=false"
        async with aiohttp.ClientSession() as session:
            async with session.put(url, json=config) as response:
                return await response.json()

    async def apply_resource(self, config):
        name = config["metadata"]["name"]
        if not name.startswith(self.prefix):
            raise ValueError(f"Name {name} needs to start with prefix {self.prefix}")

        group, version = config["apiVersion"].split("/")
        kind = config["kind"]
        url = f"{self.database.endpoint_url}/{self.database.name}/resources/{group}/{version}/{kind}/{name}?create=true"
        data = json.dumps(config)
        headers = {"Content-Type": "application/json"}
        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers=headers, data=data) as response:
                text = await response.text()
                # return await response.json()
                return json.loads(text)

    async def delete_resource(self, group, version, kind, name):
        if not name.startswith(self.prefix):
            raise ValueError(f"Name {name} needs to start with prefix {self.prefix}")

        url = f"{self.database.endpoint_url}/{self.database.name}/resources/{group}/{version}/{kind}/{name}"
        async with aiohttp.ClientSession() as session:
            async with session.delete(url) as response:
                return await response.json()

    async def read_queue(
        self, group=None, version=None, kind=None, name=None, utctime=None
    ):
        if name and not name.startswith(self.prefix):
            raise ValueError(f"Name {name} needs to start with prefix {self.prefix}")

        url = f"{self.database.endpoint_url}/{self.database.name}/queue"
        params = {}
        if group:
            params["group"] = group
        if version:
            params["version"] = version
        if kind:
            params["kind"] = kind
        if name:
            params["name"] = name
        else:
            params["prefix"] = self.prefix
        if utctime:
            params["timestamp"] = utctime

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                return await response.json()

    async def lock_resource(self, group, version, kind, name):
        if not name.startswith(self.prefix):
            raise ValueError(f"Name {name} needs to start with prefix {self.prefix}")

        url = f"{self.database.endpoint_url}/{self.database.name}/claim/{group}/{version}/{kind}/{name}"

        async with aiohttp.ClientSession() as session:
            async with session.post(url) as response:
                return await response.json()

    async def unlock_resource(self, group, version, kind, name):
        if not name.startswith(self.prefix):
            raise ValueError(f"Name {name} needs to start with prefix {self.prefix}")

        url = f"{self.database.endpoint_url}/{self.database.name}/release-claim/{group}/{version}/{kind}/{name}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url) as response:
                return await response.json()

    async def resolve_resource(
        self, group, version, kind, name, config, operations, delete=False, force=False
    ):
        if not name.startswith(self.prefix):
            raise ValueError(f"Name {name} needs to start with prefix {self.prefix}")

        url = f"{self.database.endpoint_url}/{self.database.name}/resolve-claim/{group}/{version}/{kind}/{name}?force={force}"
        data = {"operations": operations, "delete": delete}
        if config != None:
            data["config"] = config

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                return await response.json()

    def control_resource(self, group, version, kind, name, validate=False):
        if not name.startswith(self.prefix):
            raise ValueError(f"Name {name} needs to start with prefix {self.prefix}")

        return BaseController(self, group, version, kind, name, validate=validate)


class BaseController:
    def __init__(
        self, config_ops: ClusterOperations, group, version, kind, name, validate=False
    ):
        self.config_ops = config_ops
        self.group = group
        self.version = version
        self.kind = kind
        self.name = name
        self.validate = validate

        self.pending_ops = None
        self.processed_op_ids = set()
        self.observed_op_ids = set()

        self.have_current_config = False
        self.current_config = None
        self.delete_current = False
        self.locked_config_name = None

    async def __aenter__(self):
        await self.acquire_object()

    async def __aexit__(self, exc_type, exc, tb):
        await self.release_current_object()

    async def acquire_object(self):
        initial_ops = await self.config_ops.lock_resource(
            self.group, self.version, self.kind, name=self.name
        )
        self.locked = initial_ops != []

        if initial_ops:
            self.locked_config_name = initial_ops[0]["name"]
        else:
            self.locked_config_name = None

        self.current_config = None
        self.delete_current = False
        self.have_current_config = False
        self.pending_ops = sorted(initial_ops, key=lambda x: x["timestamp"])

    async def release_current_object(self):
        if self.locked_config_name == None:
            return

        await self.config_ops.resolve_resource(
            self.group,
            self.version,
            self.kind,
            self.locked_config_name,
            self.current_config,
            list(self.processed_op_ids),
            delete=self.delete_current,
            force=True,
        )

        self.locked_config_name = None
        self.current_config = None
        self.delete_current = False
        self.have_current_config = False
        self.processed_op_ids = set()

    async def next_operation_batch(self):
        if self.locked_config_name == None:
            return

        force = self.observed_op_ids != self.processed_op_ids
        if force:
            print(
                "Warning: release config lock because not all operations were processed"
            )

        new_ops = await self.config_ops.resolve_resource(
            self.group,
            self.version,
            self.kind,
            self.locked_config_name,
            self.current_config,
            list(self.processed_op_ids),
            delete=self.delete_current,
            force=force,
        )

        self.processed_op_ids = set()

        # If there are new operations for this object, queue them
        if new_ops:
            self.pending_ops = sorted(new_ops, key=lambda x: x["timestamp"])
        elif not self.name:
            # If there are no new operations for this object, check other objects if needed
            self.locked_config_name = None
            await self.acquire_object()
        else:
            self.locked_config_name = None

    def __aiter__(self):
        return self

    async def get_next_operation(self):
        if self.locked_config_name == None:
            raise StopAsyncIteration()

        if not self.pending_ops:
            await self.next_operation_batch()

        if not self.pending_ops:
            raise StopAsyncIteration()

        # Return the next operation
        result = self.pending_ops.pop(0)
        self.observed_op_ids.add(result["id"])
        return PendingOperation(self, result)

    async def __anext__(self):
        result = await self.get_next_operation()
        if not self.validate:
            return result

        while True:
            if await result.validate():
                return result
            await result.reject()
            result = await self.get_next_operation()

    async def get_current_config(self):
        if self.have_current_config == False:
            self.current_config = await self.config_ops.read_resource(
                self.group, self.version, self.kind, self.locked_config_name
            )
            self.have_current_config = True

        return self.current_config

    async def accept(self, pendingOp, new_config=None, delete=None):
        if pendingOp.data["id"] in self.processed_op_ids:
            raise ValueError(f"Operation {pendingOp['id']} already processed")

        self.processed_op_ids.add(pendingOp.data["id"])

        self.current_config = new_config or await pendingOp.new_config()

        if delete == None:
            self.delete_current = pendingOp.data["operation"] == "DELETE"
        else:
            self.delete_current = delete

    async def reject(self, pendingOp):
        if pendingOp.data["id"] in self.processed_op_ids:
            raise ValueError(f"Operation {pendingOp.data['id']} already processed")

        self.processed_op_ids.add(pendingOp.data["id"])


class PendingOperation:
    def __init__(self, controller: BaseController, data):
        self.controller = controller
        self.data = data

    async def old_config(self):
        return await self.controller.get_current_config()

    async def new_config(self):
        if self.data["operation"] == "CREATE":
            return self.data["config"]
        elif self.data["operation"] == "DELETE":
            return None
        elif self.data["operation"] == "PATCH":
            return merge(await self.old_config(), self.data["config"])
        elif self.data["operation"] == "REPLACE":
            return self.data["config"]

    async def patch_config(self):
        return create_patch(await self.old_config(), await self.new_config())

    async def validate(self):
        if self.data["operation"] == "CREATE":
            return await self.old_config() == None
        elif self.data["operation"] == "DELETE":
            return await self.old_config() != None
        elif self.data["operation"] == "PATCH":
            return await self.old_config() != None
        elif self.data["operation"] == "REPLACE":
            if self.data["create"]:
                return True
            else:
                return await self.old_config() != None
        else:
            return False

    async def accept(self, new_config=None, delete=None):
        await self.controller.accept(self, new_config=new_config, delete=delete)

    async def reject(self):
        await self.controller.reject(self)
