"""Synthetic revision/ACL index lifecycle simulator, not a production connector."""
from dataclasses import dataclass
import hashlib


@dataclass(frozen=True)
class Snapshot:
    tenant: str
    source: str
    revision: int
    text: str
    acl: frozenset[str]
    classification: str = 'internal'
    deleted: bool = False
    chunker: str = 'chunks-v1'
    embedder: str = 'embed-v1'


class IndexSimulator:
    def __init__(self):
        self.active = {}
        self.builds = 0

    def publish(self, snapshot, *, expected_index_revision):
        key = (snapshot.tenant, snapshot.source)
        prior = self.active.get(key)
        current = prior['index_revision'] if prior else 0
        if current != expected_index_revision:
            raise ValueError('Conflicting index revision; reload and retry')
        if prior and snapshot.revision < prior['snapshot'].revision:
            raise ValueError('Stale source revision')
        if prior and snapshot.revision == prior['snapshot'].revision:
            old = prior['snapshot']
            if (snapshot.text, snapshot.acl, snapshot.classification, snapshot.deleted) != (old.text, old.acl, old.classification, old.deleted):
                raise ValueError('Same source revision has inconsistent content/security facts')
        digest = hashlib.sha256(snapshot.text.encode()).hexdigest()
        rebuild = not snapshot.deleted and (not prior or prior['digest'] != digest or
                  (prior['snapshot'].chunker, prior['snapshot'].embedder) != (snapshot.chunker, snapshot.embedder))
        if rebuild:
            self.builds += 1
        self.active[key] = {'snapshot':snapshot, 'digest':digest, 'index_revision':current+1}
        return 'deleted' if snapshot.deleted else 'rebuilt' if rebuild else 'metadata_refreshed'

    def read(self, tenant, source, principal, allowed_classifications, authority):
        key = (tenant, source)
        indexed = self.active.get(key)
        current = authority.get(key)
        if not indexed or not current or current.deleted:
            return None
        if principal not in current.acl or current.classification not in allowed_classifications:
            return None
        # Current authority cannot be replaced by a stale index filter.
        if indexed['snapshot'].revision != current.revision or indexed['snapshot'].deleted:
            return None
        return indexed['snapshot'].text
