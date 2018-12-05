from _collections_abc import dict_keys
from mombai._containers import slist, as_list, args_zip, args_to_list, eq
from mombai._decorators import getargs, try_list
from mombai._dict_utils import pass_thru, first, last
from copy import deepcopy

def _relabel(key, relabels):
    """
    >>> relabels = dict(b='BB', c = lambda value: value.upper())
    >>> assert _relabel('a', relabels) == 'a'
    >>> assert _relabel('b', relabels) == 'BB'
    >>> assert _relabel('c', relabels) == 'C'
    >>> assert _relabel(dict(a = 1, b=2, c=3), relabels) == {'a': 1, 'BB': 2, 'C': 3}
    >>> assert _relabel(dict(a = 1, b=2, c=3), lambda label: label*2) == {'aa': 1, 'bb': 2, 'cc': 3}
    >>> assert _relabel('label_volatility', 'market') == 'market_volatility'
    """
    if isinstance(key, dict):
        return type(key)({_relabel(k, relabels) : v for k, v in key.items()})
    if isinstance(relabels, str):
        return key.replace('label', relabels)
    if callable(relabels):
        return relabels(key)
    if key not in relabels:
        return key
    res = relabels[key]
    if not isinstance(res, str) and callable(res):
        return res(key)
    else:
        return res


class Dictattr(dict):
    """
    Dictattr is our base dict and inherits from dict with support to attribute access
    >>> a = Dictattr(a = 1, b = 2)
    >>> assert a['a'] == a.a
    >>> a.c = 3
    >>> assert a['c'] == 3
    >>> del a.c
    >>> assert list(a.keys()) == ['a','b']
    >>> assert a['a','b'] == [1,2]
    >>> assert a[['a','b']] == Dictattr(a = 1, b=2)
    >>> assert not a == dict(a=1,b=2)
    """
    def __sub__(self, other):
        return type(self)({key: value for key, value in self.items() if  key in self.keys() - other})
    def __and__(self, other):
        return type(self)({key: value for key, value in self.items() if  key in self.keys() & other})
    def __add__(self, other):
        res = self.copy()
        res.update(other)
        return res
    def __dir__(self):
        return list(self.keys()) + super(Dictattr, self).__dir__()
    def __getattr__(self, attr):
        return self[attr]
    def __setattr__(self, attr, value):
        self[attr] = value
    def __delattr__(self, attr):
        del self[attr]
    def __getitem__(self, value):
        if isinstance(value, tuple):
            return [self[v] for v in value]
        elif isinstance(value, (list, dict_keys)):
            return type(self)({v: self[v] for v in value})
        return super(Dictattr, self).__getitem__(value)
    def keys(self):
        return slist(super(Dictattr, self).keys())
    def values(self):
        return list(super(Dictattr, self).values())
    def copy(self):
        return type(self)(self)
    def __deepcopy__(self, *args, **kwargs):
        return type(self)({key : deepcopy(value) for key, value in self.items()})
    def __eq__(self, other):
        return eq(self, other)    

class Dict(Dictattr):
    """
    Dict inherits from dict with some key additional features. 
    The aim is to transform dict into a mini "container of variables" in our research:
     
    Here is the usual pattern of our research:
        
    def function(a,b):
        c = a + b
        d = c * a
        e = d - c
        return e
    
    def other_function(a, e):
        #note that b isn't needed
        return e+a
        
    x = dict(a=1, b=2) 
    x['e'] = function(x['a'], x['b'])
    x['f'] = other_function(x['a'], x['e'])
    
    The trouble is...:
    1) during research we are not sure if the code for function is right
    2) we don't have a visibility on what happens internally
    3) if functions fails, debugging is a pain and tracking log tricky. 
    4) we cannot even feed other_function(**x) since x has b that other_function does not want
    
    so... Dict makes this easier by inspecting the function's argument names, matching its keys to the function's kwargs:
    x = Dict(a=1, b=2) 
    x['e'] = x[function]
    x['f'] = x[other_function]

    If we want to build our result gradually, then we do this:
    x['c'] = x[lambda a,b : a+b]    
    x['d'] = x[lambda a,c : a*c]    
    x['e'] = x[lambda d,c : d-c]    
    we can run each of the lines separately and examine the result as we go along.

    We can add the new variable by applying the function: 
    x = x(c = lambda a,b : a+b)    
    x = x(d = lambda a,c : a*c)
    x = x(e = lambda d,c : d-c)
    
    allowing us to "chain operations"
    x = x(c = lambda a,b : a+b)(d = lambda a,c : a*c)(e = lambda d,c : d-c) ## or even...
    x = x(c = lambda a,b : a+b, d = lambda a,c : a*c, e = lambda d,c : d-c)    
    assert x == dict(a = 1, b=2, c=3, d=3, e=0)
    
    Dict can also be used as a mini "calculation graph/network", where we define the order of calculations and then perform them later on values:
    
    calculations = Dict(c = lambda a,b : a+b, d = lambda a,c : a*c, e = lambda d,c : d-c)
    inputs = Dict(a=1, b=2)
    values = inputs(**calculations)    
    graph = inputs + calculations
    values = Dict()(**graph)
    
    In addition, there are a few features to quicken development:
    d.apply(function, **redirects) # equivalent to d[function] but allows parameter relabeling 
    d.do(functions, *keys, **redirects) # applies a sequence of function on multiple keys, each time mapping on the same original key
    """
    def __call__(self, *relabels, **functions):
        """
        The call function allows us to assign to new keys, new values:
        >>> d = Dict(a = 1)
        >>> d = d(b = 2)
        >>> assert d == Dict(a=1,b=2)
        
        
        In addition, we can add new columns using functions of existing columns:
        >>> d = d(c = lambda a, b: a+b)
        >>> assert d == Dict(a=1,b=2,c=3)
        
        Sometime, we may have an existing function that we want to use. In which case we can map the function's args to the keys:
        >>> def add(x,y):
        >>>    return x+y
        >>> d = d(dict(x='a',y='b', z='c'), z = add) # note that we are allowed to re-label the return key as well!
        >>> assert d == Dict(a=1,b=2,c=3)

        We allow us to actually loop over multiple keys and run the function twice: 
        >>> d = d(dict(x='a',y='b',z='c'), dict(x='c',y='b',z='d'), z = add)
        >>> assert d == Dict(a=1, b=2, c=3, d=5)

        The final functionality is not for the faint of hearts. Using 'label' in the args of the function is treated as a special case. Allowing us to write succinctly: 
            
        >>> d = Dict(a=1,b=2,c=3)
        >>> d = d('b', 'c', label2 = lambda label: label**2)
        >>> assert d == Dict(a=1,b=2,c=3, b2=4, c2=9)
        >>> d = d('b','c', label_cubed_plus_a = lambda label, label2, a: label2 * label+a)
        >>> assert d == Dict({'a': 1, 'b': 2, 'c': 3, 'b2': 4, 'c2': 9, 'b_cubed_plus_a': 9, 'c_cubed_plus_a': 28})

        """
        res = self.copy()
        if len(relabels) == 0:
            relabels = [pass_thru]
        for key, value in functions.items():
            if callable(value):
                for relabel in relabels:
                    res[_relabel(key, relabel)] = res.apply(value, relabel)
            else:
                res[key] = value
        return res

    def __getitem__(self, value):
        if isinstance(value, tuple):
            return [self[v] for v in value]
        elif isinstance(value, (list, dict_keys)):
            return type(self)({v: self[v] for v in value})
        elif callable(value):
            return self.apply(value)
        return super(Dict, self).__getitem__(value)


    def _precall(self, function):
        """
        This is a placeholder, allowing classes that inherit to apply vectorization/parallelization of the call method
        """
        return function    

    def apply(self, function, relabels=None):
        """
        >>> self = Dict(a=1)
        >>> function = lambda x: x+2
        >>> assert self.apply(f, relabels = dict(x = 'a')) == 3
        >>> g = lambda col: col + 2
        >>> assert self.apply(g, lambda arg: arg.replace('col', 'a')) == 3
        
        """
        args = getargs(function)
        relabels = relabels or {}
        args2keys = {arg : _relabel(arg, relabels) for arg in args}
        parameters = {arg : self[key] for arg, key in args2keys.items() if key in self}
        return self._precall(function)(**parameters)


    def do(self, functions=None, *keys, **relabels):
        """
        Many times we want to apply a collection of function on multiple keys, 
        returning the resulting value to the same key. E.g.
        we read some data as text and and then parse and finally, just the year:
            
        >>> from dateutil import parser
        >>> to_year = lambda date: date.year
        >>> from mombai import Dict
        
        >>> d1 = Dict(issue_date = '1st Jan 2001', maturity = '2nd Feb 2010')
        >>> d2 = Dict(issue_date = '1st Jan 2001', maturity = '2nd Feb 2010')
        
        >>> d1['issue_date'] = parser.parse(d1['issue_date'])
        >>> d1['maturity'] = parser.parse(d1['maturity'])
        >>> d1['issue_date'] = to_year(d1['issue_date'])
        >>> d1['maturity'] = to_year(d1['maturity'])
        
        #instead you can:
        >>> d2 = d2.do([parser.parse, to_year], 'maturity', 'issue_date')
        >>> assert d1 == d2
        
        
        >>> d = Dict(a=1, b=2, c=3)
        >>> d = d.do(str, 'a', 'b', 'c')
        >>> assert d == Dict(a = '1', b='2', c='3')
        >>> d = d.do(lambda value, a: value+a, ['b', 'c'])
        >>> assert d == Dict(a = '1', b='21', c='31')        
        >>> assert d.do([int, lambda value, a: value-int(a)], 'b','c') == Dict(a = '1', b=20, c=30)
        
        >>> d = Dict(a=1,b=2,c=3)
        >>> assert d.do(lambda value, other: value+other, 'b','c', other = 'a') == Dict(a=1,b=3,c=4)
        >>> assert d.do(lambda value, other: value+other, 'b','c', relabels = lambda arg: arg.replace('other', 'a')) == Dict(a=1,b=3,c=4)
        """
        res = self.copy()
        keys = slist(args_to_list(keys))
        relabels = relabels.get('relabels', relabels)
        for function in as_list(functions):
            args = try_list(getargs)(function, 1) 
            if keys & args:
                raise ValueError('cannot apply args both in the function args and in the keys that need to be done as result is then order-of-operation sensitive %s'%(keys & args))
            func = res._precall(function)
            for key in keys:
                args2keys = {arg : _relabel(arg, relabels) for arg in args}
                parameters = {arg : self[key] for arg, key in args2keys.items() if key in self}
                res[key] = func(res[key], **parameters)
        return res
    
    def relabel(self, **relabels):
        """quick functionality to relabel the keys
        if existing key is not in the relabels, it stays the same
        if the relabel is another simple column name, it gets used
        if the relabel is a function, use this on the key.
        
        >>> d = Dict(a=1, b=2, c=3)
        >>> assert d.relabel(b = 'bb', c=lambda value: value.upper()) == Dict(a = 1, bb=2, C=3)
        >>> assert d.relabel(relabels = dict(b='bb', c=lambda value: value.upper())) == Dict(a=1, bb=2, C=3)
        """
        relabels = relabels.get('relabels', relabels)
        if not relabels: 
            return self
        return type(self)({_relabel(key, relabels) : value for key, value in self.items()})  

