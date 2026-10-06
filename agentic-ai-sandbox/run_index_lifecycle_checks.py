"""Demonstrate classification-only changes, rebuilds, tombstones and namespaces."""
from dataclasses import replace
from index_lifecycle_reference import Snapshot, IndexSimulator


def main():
    index = IndexSimulator()
    first = Snapshot('tenant-a','policy',1,'A synthetic policy',frozenset({'alice'}))
    authority = {('tenant-a','policy'):first}
    assert index.publish(first,expected_index_revision=0) == 'rebuilt'
    assert index.read('tenant-a','policy','alice',{'internal'},authority) == first.text
    restricted = replace(first, revision=2, classification='restricted')
    authority[('tenant-a','policy')] = restricted
    assert index.read('tenant-a','policy','alice',{'internal'},authority) is None
    assert index.publish(restricted,expected_index_revision=1) == 'metadata_refreshed'
    assert index.builds == 1, 'Security metadata changes do not require re-embedding unchanged content'
    assert index.read('tenant-a','policy','alice',{'restricted'},authority) == first.text
    rebuilt = replace(restricted, embedder='embed-v2')
    assert index.publish(rebuilt,expected_index_revision=2) == 'rebuilt' and index.builds == 2
    revoked = replace(rebuilt, revision=3, acl=frozenset({'bob'}))
    authority[('tenant-a','policy')] = revoked
    assert index.read('tenant-a','policy','alice',{'restricted'},authority) is None
    index.publish(revoked,expected_index_revision=3)
    tombstone = replace(revoked, revision=4, deleted=True)
    authority[('tenant-a','policy')] = tombstone
    index.publish(tombstone,expected_index_revision=4)
    for stale,expected in [(first,5),(tombstone,3)]:
        try:
            index.publish(stale,expected_index_revision=expected)
        except ValueError:
            pass
        else:
            raise AssertionError('Stale source or writer must be rejected')
    assert index.read('tenant-a','policy','bob',{'restricted'},authority) is None
    other = replace(first,tenant='tenant-b',text='Other tenant policy')
    authority[('tenant-b','policy')] = other
    index.publish(other,expected_index_revision=0)
    assert index.read('tenant-b','policy','alice',{'internal'},authority) == other.text
    assert index.read('tenant-a','policy','alice',{'internal'},authority) is None
    print('PASS lifecycle: classification/ACL refresh, processing rebuild, current-authority denial, tombstones, CAS and tenant namespace')


if __name__ == '__main__':
    main()
