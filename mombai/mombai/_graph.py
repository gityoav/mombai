import networkx as nx
import jsonpickle as jp
from mombai._cell import Cell, Hash, _per_cell, passthru
from mombai._containers import as_list, is_array
from mombai._dictable import Dictable
from mombai._dates import to_serializable
from functools import partial
from copy import copy, deepcopy
#from mombai import *
if False:
    from tinydb import TinyDB, Query
    db = TinyDB('db.json')
    db.insert(jp.decode(j))    
    q = Query()
    db.insert(dict(a = 1, b = 'key'))
    db.insert(dict(a = 2, b = 'key'))
    db.all()
    db.remove
    db.remove(q.a.exists())
    db.search(q.a >= 1)
    db.all()

def _is_edge(key):
    return isinstance(key, tuple) and len(key) == 2

_is_ref = lambda s: isinstance(s, str) and s.startswith('@')
_is_ref.__doc__ = "checks if a string is a reference, which by convention we prefix with @"

_is_int = lambda s: (s.startswith('-') and s[1:].isdigit()) or s.isdigit()
_is_int.__doc__ = "checks if a string is either a positive or a negative integer"

_to_id = partial(_per_cell, f = lambda v: '@%s'%(v.id if isinstance(v.node, dict) else v.node))
_to_id.__doc__ = "Converts a cell into its id. If it was a dict, then an v.id, its hash is used. Otherwise, if it is a single value, use that value as reference"


class DAG(nx.DiGraph):

    @classmethod
    def _key(cls, key):
        return key

    @classmethod
    def _as_dict(cls, value):
        if isinstance(value, dict):
            return value
        else:
            return dict(value = value)

    @classmethod
    def _as_value(cls, d):
        if len(d)==1 and 'value' in d.keys():
            return d['value']
        else:
            return d

    def __getitem__(self, key):
        key = self._key(key)
        if _is_edge(key):
            return self._as_value(self.edges[key[0], key[1]])
        else:
            return self._as_value(self.nodes[key])

    def __setitem__(self, key, value):
        key = self._key(key)
        d = self._as_dict(value)
        if _is_edge(key):
            self.add_edge(key[0], key[1], **d)
        else:
            self.add_node(key, **d)
            
    def __delitem__(self, key):
        key = self._key(key)
        if _is_edge(key):
            self.remove_edge(key[0], key[1])
        else:
            self.remove_node(key)

    def __contains__(self, key):
        key = self._key(key)
        return key in self.edges if _is_edge(key) else key in self._node
            
    def remove_node(self, node = None):
        if node is None:
            node = list(self.nodes)
        if is_array(node):
            for n in node:
                self.remove_node(n)
        else:
            super(DAG, self).remove_node(node)
    
    def remove_edge(self, u = None, v = None):
        if u is None:
            u = list(self.edges)
        if v is None and is_array(u):
            for e in u:
                self.remove_edge(*e)
        else:
            super(DAG, self).remove_edge(u,v)

DAG.__doc__ = """Additional api over networkx graph with a quicker interface and support to adding cells to it as well deleting nodes and edges en-masse
This can be implemented on all networkx graphs 

# g['node'] = node   # to set the nodes
# g['node']          # to access the node
# del g['node']      # to delete the node

# g['a', 'b'] = edge   # to set the edge from a to b
# g['a', 'b']          # to access the edge 
# del g['a', 'b']      # to delete the edge

""" + nx.DiGraph.__doc__                


def _from_id(value, graph):
    if is_array(value):
        return [_from_id(v, graph) for v in value]
    elif isinstance(value, str) and _is_ref(value):
        s = value[1:]
        return graph[int(s) if _is_int(s) else s]
    else:
        return value


class XCL(DAG):
    @classmethod
    def _key(self, key):
        """
        converts key into the Hash handling:
            if key is an edge, returns the edge pair
            if key is a ref, i.e. @id, will convert to an id first and if an int, to an int
            if key is a cell itself, will use the cell.node. This allows graph[cell] = cell code
        """
        if _is_edge(key):
            return (self._key(key[0]), self._key(key[1]))
        if _is_ref(key):
            key = key[1:]
            if _is_int(key):
                key = int(key)
        if isinstance(key, Cell):
            return self._key(key.node)
        return Hash(key)

    @classmethod
    def _as_dict(cls, value):
        if isinstance(value, dict) and not isinstance(value, Cell):
            return value
        else:
            return dict(value = value)

    def __setitem__(self, key, value):
        if _is_edge(key):
            d = self._as_dict(value)
            key = self._key(key)
            self.add_edge(key[0], key[1], **d)
        else:
            d = self._as_dict(value if isinstance(value, Cell) else Cell(key, value))
            key = self._key(key)
            self.add_node(key, **d)

    def __add__(self, cell):
        graph = self
        if isinstance(cell, Cell):
            graph[cell.node] = cell
            graph = graph + cell.function
            graph = graph + list(cell.args)
            graph = graph + list(cell.kwargs.values())
        elif is_array(cell):
            for c in cell:
                graph = graph + c                 
        return graph
    
    def to_id(self):
        """
        We start with a graph where each cell can contain other cells:
        >>> from mombai import *
        >>> from operator import add
        >>> g = XCL()        
        >>> g['a'] = Cell('a', 1)        
        >>> g['b'] = Cell('b', 2)
        >>> g['c'] = Cell('c', add, g['a'], g['b']) 
        >>> assert g['c']() == 3
        >>> h = g.to_id()
    
        Now if we convert to ids, cell c will point to a and b
        >>> assert h['a'] == g['a']
        >>> assert h['b'] == g['b']
        >>> assert h['c']() == '@a@b'
        
        g = g.add_parents()
        h = h.add_parents()
        assert g.edges == h.edges
        
        """
        result = deepcopy(self)
        for node in result.nodes:
            c = copy(result[node])
            c.function = _to_id(c.function)
            c.args = _to_id(c.args)
            c.kwargs = {key : _to_id(value) for key, value in c.kwargs.items()}
            result[node] = c
        return result

    def from_id(self):
        """
        This converts a graph with variable of references ids into a graph with actual cells in the kwargs and args
        We do need the graph to already have 
        """
        result = deepcopy(self)
        for node in nx.topological_sort(self):
            c = result[node]
            c.function = _from_id(c.function, result)
            c.args = _from_id(c.args, result)
            c.kwargs = {key : _from_id(value, result) for key, value in c.kwargs.items()}
            result[node] = c
        return result        
            
    def add_parents(self, cell=None, parent=None):
        """
        Loops through chosen cell and parents and add them to the edges
        """
        graph = self
        if cell is None:
            cell = [graph[c] for c in graph.nodes]
        if _is_ref(cell):
            cell = graph[cell]
        elif is_array(cell):
            for c in cell:
                graph = graph.add_parents(c, parent)
        if isinstance(cell, Cell):
            if isinstance(parent, Cell) or _is_ref(parent):
                graph[parent, cell] = {} # this is where the action is
            elif is_array(parent):
                for p in parent:
                    graph = graph.add_parents(cell, p)
            elif parent is None:
                graph = graph.add_parents(cell, cell.function)
                graph = graph.add_parents(cell, list(cell.args))
                graph = graph.add_parents(cell, list(cell.kwargs.values()))
        return graph

    def to_table(self):
        rs = Dictable(node_id = list(nx.topological_sort(self)))
        rs = rs(node = lambda node_id: self[node_id])
        rs = rs(function = lambda node: node.function)
        rs = rs(args = lambda node: node.args)
        rs = rs(kwargs = lambda node: node.kwargs)
        rs = rs(node = lambda node: node.node)
        return rs
    
    def __repr__(self):
        return self.to_table().__repr__()

    def __str__(self):
        return self.to_table().__str__()

    def metadata(self):
        """
        This version returns a list of dict per node that can be then pushed into a tinydb database for querying. We delegate the actual keys that are important to the cell.metadata() implementation
        """
        i = self.to_id()
        m = {k : i[k].metadata() for k in i._node}
        return m        
        
    def to_json(self):
        """
        We drop all edge information encoding only the nodes and before that, de-reference the nodes
        """
        i = self.to_id()
        j = jp.encode({k : i[k] for k in i._node})
        return j
    
    @classmethod
    def from_json(cls, j):
        """
        We construct the graph from the minimal json with only the dict of nodes
        We then add the parental graph
        We finally dereference the nodes
        """
        minimal = {int(k) if _is_int(k) else k: v for k, v in jp.decode(j).items()}
        res = cls()
        for k, v in minimal.items():
            res[k] = v
        res = res.add_parents()
        res = res.from_id()
        return res

XCL.__doc__ = """Added feauture: keys are always hashed but can be accessed either by the hash or the original value, 
Support for adding Cell to the graph, adding for each cell its parents automatically\n\n
""" + DAG.__doc__
              
