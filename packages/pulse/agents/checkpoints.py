from langgraph.checkpoint.base import WRITES_IDX_MAP, BaseCheckpointSaver, CheckpointTuple
from sqlalchemy import select

from pulse.db.models import Checkpoint, CheckpointWrite


class DatabaseSaver(BaseCheckpointSaver):
    """LangGraph checkpoints and pending writes use the same persistent database as incidents."""

    def __init__(self, store):
        super().__init__()
        self.store = store

    @staticmethod
    def config(thread, namespace, checkpoint):
        return {
            "configurable": {
                "thread_id": thread,
                "checkpoint_ns": namespace,
                "checkpoint_id": checkpoint,
            }
        }

    def unpack(self, row, db):
        writes = db.scalars(
            select(CheckpointWrite)
            .where(
                CheckpointWrite.thread_id == row.thread_id,
                CheckpointWrite.checkpoint_ns == row.checkpoint_ns,
                CheckpointWrite.checkpoint_id == row.checkpoint_id,
            )
            .order_by(CheckpointWrite.task_id, CheckpointWrite.idx)
        ).all()
        return CheckpointTuple(
            config=self.config(row.thread_id, row.checkpoint_ns, row.checkpoint_id),
            checkpoint=self.serde.loads_typed(
                (row.checkpoint_type, bytes.fromhex(row.checkpoint_blob))
            ),
            metadata=self.serde.loads_typed((row.metadata_type, bytes.fromhex(row.metadata_blob))),
            parent_config=self.config(row.thread_id, row.checkpoint_ns, row.parent_id)
            if row.parent_id
            else None,
            pending_writes=[
                (
                    w.task_id,
                    w.channel,
                    self.serde.loads_typed((w.value_type, bytes.fromhex(w.value_blob))),
                )
                for w in writes
            ],
        )

    def get_tuple(self, config):
        conf = config["configurable"]
        with self.store.session() as db:
            query = select(Checkpoint).where(
                Checkpoint.thread_id == conf["thread_id"],
                Checkpoint.checkpoint_ns == conf.get("checkpoint_ns", ""),
            )
            if conf.get("checkpoint_id"):
                query = query.where(Checkpoint.checkpoint_id == conf["checkpoint_id"])
            row = db.scalar(query.order_by(Checkpoint.checkpoint_id.desc()).limit(1))
            return self.unpack(row, db) if row else None

    def list(self, config, *, filter=None, before=None, limit=None):
        with self.store.session() as db:
            query = select(Checkpoint)
            if config:
                conf = config["configurable"]
                query = query.where(
                    Checkpoint.thread_id == conf["thread_id"],
                    Checkpoint.checkpoint_ns == conf.get("checkpoint_ns", ""),
                )
            if before:
                query = query.where(
                    Checkpoint.checkpoint_id < before["configurable"]["checkpoint_id"]
                )
            count = 0
            for row in db.scalars(query.order_by(Checkpoint.checkpoint_id.desc())):
                item = self.unpack(row, db)
                if filter and not all(item.metadata.get(k) == v for k, v in filter.items()):
                    continue
                yield item
                count += 1
                if limit and count >= limit:
                    break

    def put(self, config, checkpoint, metadata, new_versions):
        conf = config["configurable"]
        ctype, cblob = self.serde.dumps_typed(checkpoint)
        mtype, mblob = self.serde.dumps_typed(metadata)
        with self.store.session.begin() as db:
            db.merge(
                Checkpoint(
                    thread_id=conf["thread_id"],
                    checkpoint_ns=conf.get("checkpoint_ns", ""),
                    checkpoint_id=checkpoint["id"],
                    parent_id=conf.get("checkpoint_id"),
                    checkpoint_type=ctype,
                    checkpoint_blob=cblob.hex(),
                    metadata_type=mtype,
                    metadata_blob=mblob.hex(),
                )
            )
        return self.config(conf["thread_id"], conf.get("checkpoint_ns", ""), checkpoint["id"])

    def put_writes(self, config, writes, task_id, task_path=""):
        conf = config["configurable"]
        with self.store.session.begin() as db:
            for i, (channel, value) in enumerate(writes):
                idx = WRITES_IDX_MAP.get(channel, i)
                key = (
                    conf["thread_id"],
                    conf.get("checkpoint_ns", ""),
                    conf["checkpoint_id"],
                    task_id,
                    idx,
                )
                if idx >= 0 and db.get(CheckpointWrite, key):
                    continue
                vtype, vblob = self.serde.dumps_typed(value)
                db.merge(
                    CheckpointWrite(
                        thread_id=key[0],
                        checkpoint_ns=key[1],
                        checkpoint_id=key[2],
                        task_id=task_id,
                        idx=idx,
                        channel=channel,
                        value_type=vtype,
                        value_blob=vblob.hex(),
                    )
                )

    async def aget_tuple(self, config):
        return self.get_tuple(config)

    async def alist(self, config, *, filter=None, before=None, limit=None):
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(self, config, checkpoint, metadata, new_versions):
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        self.put_writes(config, writes, task_id, task_path)
