# -*- coding: utf-8 -*-
"""
means to cover hierarchy issues in a fully abstract way
"""

from itertools import chain, ifilter
import logging
from collections import namedtuple

log = logging.getLogger(__name__.split('.')[-1])

HierarchyDifference = namedtuple('HierarchyDifference', 'key_path key a b parent_a parent_b level vtype')


def compare_hierarchy(a, b):
    """
    compares two hierarchies
    :yields: HierarchyDifference

    :param a: one thing
    :param b: another thing
    """
    stack = []

    def yield_value(k, a, b, parent_a, parent_b, level, vtype='value'):
        return HierarchyDifference(stack, k, a, b, parent_a, parent_b, level, vtype)

    def iterthing(x):
        """
        just to unify iterators
        """
        if isinstance(x, list):
            return enumerate(x)
        elif isinstance(x, dict):
            return x.iteritems()

    def current():
        if stack:
            return stack[-1]

    def descent(k, a, b, parent_a=None, parent_b=None, level=0):
        if isinstance(a, (list, dict)):
            if len(a) != len(b):
                yield yield_value(current(), len(a), len(b), parent_a, parent_b, level, 'len')

            # despite the len difference we try to compare the rest we get - somewhat difficult for distionaries
            for k, v in iterthing(a):
                if isinstance(v, (list, dict)):

                    stack.append(k)
                    try:
                        for difference in descent(k, a[k], b[k], a, b, level + 1):
                            yield difference
                    except IndexError:
                        yield yield_value(k, k, None, a, b, level, 'index')
                    stack.pop()
                else:
                    try:
                        if a[k] != b[k]:
                            yield yield_value(k, a[k], b[k], a, b, level)
                    except KeyError:
                        yield yield_value(k, k, None, a, b, level, 'key')
        else:
            # just for comparing non iterables
            if a != b:
                yield yield_value(k, a, b, None, None, level)

    for diff in descent(None, a, b):
        yield diff


class HierarchyNode(dict):  # pylint: disable=R0904
    """
    a dict, with parent child relations
    for easy output hierarchical structures without headaches e.g. to json
    """
    _parent = None

    def __init__(self, *args, **kw):
        """
        creates a node
        :param parent: the parent of this node
        """
        self.children = list()
        self.parent = None

        dict.__init__(self, *args, **kw)
        self.rename_children('children')

    def __getattr__(self, name):
        """
        just to have the dict items also as attributes
        :raises: AttributeError if neither attribute nor key was found
        """
        try:
            return dict.__getattribute__(self, name)
        except AttributeError:
            try:
                return self[name]
            except KeyError:
                raise AttributeError('%s has neither an attribute nor a dictionary key of that name: %s' % (self.__class__.__name__, name))

    def rename_children(self, name):
        """
        gives the children another name
        """
        for k, v in self.iteritems():
            if v == self.children:
                del self[k]
                break
        self[name] = self.children

    def _set_parent(self, parent):
        """
        creates a parent child relation by also appending/removing the child to/from a parent
        """
        # only if something changes
        if self._parent != parent:
            # if we move from an existing parent
            if self._parent:
                try:
                    # remove existing children relation
                    self._parent.children.remove(self)
                except ValueError:
                    # that should never happen - so somebody must have played with the attributes...
                    log.error('''HistoryNode has a parent, but the parent doesn't know about it: %s''' % vars(self))
                    raise
            self._parent = parent
            if isinstance(self._parent, HierarchyNode):
                self._parent.children.append(self)

    def _get_parent(self):
        return self._parent
    parent = property(fset=_set_parent, fget=_get_parent)

    @property
    def parents(self):
        """
        :returns: a list of parents
        """
        parents = []
        parent = self.parent
        while parent:
            parents.append(parent)
            parent = parent.parent
        return parents

    @property
    def depth(self):
        return len(self.parents)

    @property
    def relatives(self):
        """
        @returns: all relatives of this item including itself
        """
        return self.parents + [self] + list(chain(*([c] + c.children for c in self.children)))


class HierarchyList(list):
    """
    Designed to created a hierarchy with a minimal set of information about,
    so you can use this structure to easily respond with json.
    HierarchyList takes care for indexing nodes and "put them in formation"
    """

    def __init__(self, iterable,
                 callback=None,
                 get_id_func=lambda item: getattr(item, 'id'),
                 get_parent_id_func=lambda item: getattr(item, 'parent_id')):
        """
        creates an index and the root list
        the json encoder will only "see" the list content
        as children are HierarchyNodes of base dict, the json enocder will only see the dict contents.
        So you can put additional attributes to the nodes without disturbing the json output.

        :param iterable: an iterable list
        :type iterable: iterable list
        :param callback: a function which is called for further processing the item and its node
        :type callback: func(item, node, hierarchy_list)
        :param get_id_func: the function is returning the id of an item
        :type get_id_func: func(item) - returns unique key
        :param get_parent_id_func: the function is returning the parent_id of an item
        :type get_parent_id_func: func(item) - returns unique key
        """
        list.__init__(self)
        self.idx = dict()
        self.children = set()

        for item in iterable:
            node = self.establish_node(get_id_func(item), get_parent_id_func(item))
            # enrichment with cross data
            callback and hasattr(callback, '__call__') and callback(item, node, self)   # pylint: disable=W0106

    def establish_node(self, n_id, n_parent_id=None):
        """
        creates a node and connects it to its parent or creates it
        every established node/parent is inserted into the index resp. root list

        :param n_id: the id of the node
        :param n_parent_id: the id of the parent node
        :returns: HierarchyNode - the indexed node
        """
        node = self.find_or_create_node(n_id)
        # add this item to the children
        self.children.add(n_id)
        if n_parent_id:
            node.parent = self.find_or_create_node(n_parent_id)
        else:
            self.append(node)
        return node

    @property
    def parents(self):
        """
        :returns: the opposite of self.children - a set of nodes which are not reference as a child
        """
        return set(self.idx.keys()) - self.children

    def list_generator(self, depth=3, filter_fun=None, filter_children=True):
        """
        iterates over this hierarchy list till a certain level
        additionally you can filter certain items

        this should preserve a certain order like coming from the database

        :param depth: the depth 0..3
        :param filter_fun: the filter function returns True for exclusion of items and sub items
        :type filter_fun: function (item, depth)
        :param filter_children: set to True if the children of a filtered item should also be filtered

        :returns: list - the taxonomy items in a list
        """
        def descent(itemlist, depth=0):
            """
            recursive descending
            """
            for child in itemlist:
                filtered = filter_fun and hasattr(filter_fun, '__call__') and filter_fun(child, depth)
                if not filtered:
                    yield child
                if (not filtered or not filter_children) and depth > 0:
                    for i in descent(child.children, depth - 1):
                        yield i
        for i in descent(self, depth):
            yield i

    def sort(self, key, reverse=False):
        """
        sorts the hierarchy according to the key func
        """
        def descent(itemlist):
            for child in itemlist:
                if child.children:
                    child.children = sorted(child.children, key=key, reverse=reverse)
                    descent(child.children)

        # sort toplevel
        list.sort(self, key=key, reverse=reverse)
        descent(self)


    def find_or_create_node(self, n_id):
        """
        either finds a node in the index or creates this nod with the id and indexes it

        :param n_id: the id of that node
        :returns: HierarchyNode - the found or created node
        """
        if not n_id in self.idx:
            self.idx[n_id] = HierarchyNode()
        return self.idx[n_id]

    def iterindex(self):
        """iterates over the whole index"""
        return self.idx.values()

    def iterleaves(self):
        """returns only leaves of the index"""
        return (item for item in self.iterindex() if not item.children)

    def iternodes(self):
        """returns only parents resp. no leaves of the index"""
        return (item for item in self.iterindex() if item.children)

    def iterfilter(self, fun):
        return ifilter(fun, self.idx.iteritems())

    def flying_roots(self):
        "returns a list of flying roots of this hierarchy: nodes which are not children of other nodes"
