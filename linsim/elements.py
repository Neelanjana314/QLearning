"""
This module defines the Element class and its derivatives. They are the atomic
parts of a netlist/circuit.
"""

import re


class Element:
    """
    The Element class represents a single component in a netlist.
    All arguments are case insensitive. Internally all arguments are parsed as
    lowercase strings.

    Args:
        definition (str): A netlist definition of the element. Of the form:
            <PREFIX><ID> <NODE1>... <VALUE1>... [<PARAM1>=<VALUE1>...]
        OR:
        *args: Any number of value arguments for the element. Of the form:
            <PREFIX><ID>, <NODE1>,..., <VALUE1>,...
        **kwargs: Any number of keyword=value arguments for the element.
            num_nodes (int): An optional param to override Element.num_nodes
                for the particular instance.

    Class Attributes:
        num_nodes (int): Number of nodes element is connected to.
        prefix (str): Prefix for element definition (e.g. 'R' for resistors).
        name (str): Element type (e.g. Resistor, Capacitor)
        value_regex (str): Regular expression pattern to match all single
            values in: VALUE1 VALUE2 PARAM1=VALUE3 PARAM2=VALUE4
        param_regex: Regular expression pattern to match all PARAM=VALUE pairs.
    """
    num_nodes = 2
    prefix = ''
    name = 'Element'
    value_regex = r'(?:^|\s+)((?<!=)[\w_\.]+(?=(?:$|\s+)))'
    pair_regex = r'([\w]+=[^=]+?(?=(?:$|(?:\s+\S+=))))'

    def __init__(self, *args, **kwargs):
        if 'definition' in kwargs:
            definition = kwargs.get('definition').lower()
            del kwargs['definition']
        else:
            definition = ''
        if 'num_nodes' in kwargs:
            self.num_nodes = kwargs.get('num_nodes')
        else:
            self.num_nodes = self.__class__.num_nodes

        self.args = [str(x).lower() for x in args]
        self.kwargs = {str(k).lower(): str(v).lower() for k, v in kwargs.items()}
        self.nodes = []
        self.name = ''
        self.value = ''
        if len(definition):
            self._parse_definition(definition)
        else:
            self._parse_args()


    def __str__(self):
        """
        Returns a netlist description of the element.
        """
        return self.name + ' ' + ' '.join(self.nodes) + ' ' + str(self.value) + \
                ' ' + ' '.join([k+'='+v for k, v in self.kwargs.items()])


    def param(self, param, value=None):
        """
        Returns/sets value for a param=value pair.

        Args:
            param (str): Parameter name.
            value (str/list/number): Value to set for param. If value='', param
                is deleted. Default is None in which case value for param is
                returned.

        Returns:
            Value for param if no value is provided. If a value is provided,
            returns nothing.
        """
        if value is None:
            return self.kwargs.get(param)
        else:
            if value == '':
                del self.kwargs[param]
            else:
                self.kwargs[param] = value


    def _parse_definition(self, definition):
        """
        Parses the definition and assigns attributes to instance accordingly.
        """
        split = definition.split()
        if len(split) < 1 + self.__class__.num_nodes + 1:
            # At least 1 name + num_nodes + 1 value
            raise AttributeError('Element definition does not have enough args.')
        if self.__class__.prefix.lower() != split[0][:len(self.__class__.prefix)]:
            raise ValueError('Incorrect element type.')

        self.name = split[0]
        self.nodes = [x for x in split[1:1+self.num_nodes]]

        # Construct the remaining value and param=value pair string
        value_str = ' '.join(split[1+self.num_nodes:])
        #   These subs are to comply with the regex pattern
        #   Remove trailing whitespace on = and separators
        value_str = re.sub(' = ', '=', value_str)
        value_str = re.sub('(?P<sep>[,;-_])\\s+', '\\g<sep>', value_str)

        # Isolate single values
        values = re.findall(self.__class__.value_regex, value_str)
        if values:
            self.value = self._parse_values(values)

        # Isolate key=value pairs
        pairs = re.findall(self.__class__.pair_regex, value_str)
        if pairs:
            self.kwargs = {p[0].strip(): p[1].strip() for p in
                           [pair.split('=') for pair in pairs]}
            self.kwargs = self._parse_pairs(self.kwargs)
            for key, value in self.kwargs.items():
                setattr(self, key, value)


    def _parse_values(self, values):
        """
        Processes the single values string in definition. The returned value is
        assigned to self.value.
        Override this function to control what gets assigned to self.value.

        Args:
            values (list): A list of values from the definition string.

        Returns:
            String of value elements joined by space.
        """
        return ' '.join(values)


    def _parse_pairs(self, pairs):
        """
        Processes the param=value pairs in definition. The returned dictionary
        is assigned as self.KEY = VALUE for all keys in the dictionary.
        Override this function to control what attributes get assigned to self.

        Args:
            pairs (dict): A dictionary of {PARAM: VALUE}

        Returns:
            The unchanged pairs dictionary.
        """
        return pairs


    def _parse_args(self):
        """
        Parses positional and keyword arguments provied in lieu of element
        definition string. Positional arguments are stored in self.args.
        Keyword arguments are stored in self.kwargs.
        """
        if len(self.args) < 1 + self.__class__.num_nodes + 1:
            # At least 1 name + num_nodes + 1 value
            raise AttributeError('Element definition does not have enough args.')
        if self.__class__.prefix.lower() != self.args[0][:len(self.__class__.prefix)]:
            raise ValueError('Incorrect element type.')

        self.name = self.args[0]
        self.nodes = self.args[1:1+self.num_nodes]
        self.value = self._parse_values(self.args[1+self.num_nodes:])
        self.kwargs = self._parse_pairs(self.kwargs)
        for key, value in self.kwargs.items():
            setattr(self, key, value)





class ElementMux:
    """
    Element mux maintains a set of Element subclasses so an element
    definition can be instantiated into a particular subclass based on the
    element prefix. If no match with a subclass is found, the generic Element
    instance is returned.
    This assumes that subclasses may have partially common prefixes ('a', 'ab').
    So it matches with longer prefixes first and works its way down to shortest
    prefixes.

    Args:
        root (class): A class object whose subclasses will be instantiated
            based on the element prefix. Defaults to Element.

    Class Attributes:
        identifier (func): A function that returns the identifier for an element.
            Default returns the class prefix attribute.
    """

    identifier = lambda x: x.prefix

    def __init__(self, root=Element):
        self.subclasses = []
        self.prefix_list = []
        self._mux = {}
        self.find_subclasses(root)
        self.set_up_mux()


    def find_subclasses(self, root):
        """
        Uses DFS to find all subclasses

       Args:
        root (class): A class object whose subclasses will be instantiated
            based on the element prefix. Defaults to Element.
        """
        self.root = root
        source = []
        sink = []
        source.extend(root.__subclasses__())

        while len(source):
            subclass = source.pop()
            source.extend(subclass.__subclasses__())
            sink.append(subclass)
        self.subclasses = sink


    def set_up_mux(self):
        """
        Creates a multiplexer that self.mux uses to generate a class instance.
        """
        self._mux = {self.__class__.identifier(c):c for c in self.subclasses}
        self.prefix_list = list(self._mux.keys())
        self.prefix_list.sort(reverse=True, key=len)


    def mux(self, definition):
        """
        Creates instance of a specific subclass based on matching name with
        prefix.

        Args:
            definition (str): The element definition in the netlist.

        Returns:
            An instance of the subclass of the class provided as root (defaults
            to Element)
        """
        for subclass in self.prefix_list:
            if definition[:len(subclass)] == subclass:
                return self._mux.get(subclass)(definition=definition)
        return self.root(definition=definition)
