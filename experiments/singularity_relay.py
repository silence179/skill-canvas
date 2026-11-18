"""Relay bytes between a private Unix socket and one fixed model proxy."""

import asyncio
from functools import partial
import sys


async def copy_stream(reader, writer):
    while data := await reader.read(65536):
        writer.write(data)
        await writer.drain()
    writer.write_eof()


async def relay(reader, writer, *, connect):
    upstream = None
    try:
        remote, upstream = await connect()
        async with asyncio.TaskGroup() as group:
            group.create_task(copy_stream(reader, upstream))
            group.create_task(copy_stream(remote, writer))
    except* OSError:
        pass
    finally:
        writer.close()
        if upstream is not None:
            upstream.close()


async def listen(socket_path, port):
    connect = partial(asyncio.open_unix_connection, socket_path)
    async with await asyncio.start_server(partial(relay, connect=connect), "127.0.0.1", port) as server:
        print("ready", flush=True)
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(listen(sys.argv[1], int(sys.argv[2])))
