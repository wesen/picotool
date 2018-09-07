import argparse
from typing import Union

from pico8 import util
from pico8.game import game
from pico8.lua import lua, parser, lexer


def _get_argparser():
    parser = argparse.ArgumentParser()
    parser.add_argument('infile', type=str,
                        help='the cart to turn upside down; can be .p8 '
                             'or .p8.png')
    return parser


class SideEffectGraphWalker(lua.BaseASTWalker):
    pass


# noinspection PyPep8Naming,PyMethodMayBeStatic
class UsageGraphWalker(lua.BaseASTWalker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.using = {}
        self.used_by = {}
        self.names = []
        self.depth = 0

    def walk_children(self, node):
        for field in node._fields:
            for t in self._walk(getattr(node, field)):
                yield t
                self._post_walk(getattr(node, field))

    @staticmethod
    def get_var_name(node: Union[parser.VarAttribute, parser.VarIndex, parser.VarName]):
        if isinstance(node, parser.VarName):
            return node.name.value.decode('latin1')
        elif isinstance(node, parser.VarAttribute):
            return '{}.{}'.format(UsageGraphWalker.get_var_name(node.exp_prefix), node.attr_name.value.decode('latin1'))
        elif isinstance(node, parser.VarIndex):
            return '{}[{}]'.format(UsageGraphWalker.get_var_name(node.exp_prefix), node.exp_index)
        else:
            raise RuntimeError("Unsupported node type: {}".format(type(node)))

    def lprint(self, str):
        print('{}{}'.format('   ' * self.depth, str))

    def _walk_FunctionCall(self, node):
        self.lprint(node)
        for t in self.walk_children(node):
            yield t

    def _walk_StatFunction(self, node):
        name = ".".join([t.value.decode('latin1') for t in node.funcname.namepath])
        if hasattr(node.funcname, 'methodname') and node.funcname.methodname is not None:
            name += ":" + node.funcname.methodname.value.decode('latin1')
        self.lprint("Entering function {}".format(name))
        self.names.append(name)
        self.depth += 1
        for t in self.walk_children(node):
            yield t

    def _walk_StatAssignment(self, node: parser.StatAssignment):
        # VarAttribute or VarName
        varname = UsageGraphWalker.get_var_name(node.varlist.vars[0])
        self.names.append(varname)
        self.lprint("Entering assignment {}".format(varname))
        self.depth += 1
        for t in self.walk_children(node):
            yield t

    def _post_walk_StatFunction(self, node: parser.StatFunction):
        self.lprint("Post Function {}".format(node))
        fname = self.names.pop()
        self.lprint("Leaving function {}".format(fname))
        self.depth -= 1

    def _post_walk_StatAssignment(self, node: parser.StatAssignment):
        self.lprint("Post Assignment {}".format(node))
        varname = self.names.pop()
        self.lprint("Leaving assignment {}".format(varname))
        self.depth -= 1

    def _walk_FunctionName(self, node: parser.FunctionName):
        self.lprint("Function {}".format(node))
        yield

    def _walk_VarName(self, node):
        self.lprint("Var {}".format(node))
        yield

    def _walk_NameList(self, node):
        self.lprint("NameList {}".format(node))
        yield


def get_token_count(tokens):
    c = 0
    for t in tokens:
        # TODO: As of 0.1.8, "1 .. 5" is three tokens, "1..5" is one token
        if (t.matches(lexer.TokSymbol(b':')) or
                t.matches(lexer.TokSymbol(b'.')) or
                t.matches(lexer.TokSymbol(b')')) or
                t.matches(lexer.TokSymbol(b']')) or
                t.matches(lexer.TokSymbol(b'}')) or
                t.matches(lexer.TokKeyword(b'local')) or
                t.matches(lexer.TokKeyword(b'end'))):
            # Pico-8 generously does not count these as tokens.
            pass
        elif t.matches(lexer.TokNumber) and t._data.find(b'e') != -1:
            # Pico-8 counts 'e' part of number as a separate token.
            c += 2
        elif (not isinstance(t, lexer.TokSpace) and
              not isinstance(t, lexer.TokNewline) and
              not isinstance(t, lexer.TokComment)):
            c += 1
    return c


def print_token_counts(v, counts):
    if isinstance(v, parser.Node):
        for f in v._fields:
            print_token_counts(getattr(v, f), counts)
    elif isinstance(v, list) or isinstance(v, tuple):
        for v_ in v:
            if isinstance(v_, parser.StatFunction):
                # print_token_counts(v_, counts, v_.funcname.
                name = ".".join([t.value.decode('latin1') for t in v_.funcname.namepath])
                if hasattr(v_.funcname, 'methodname') and v_.funcname.methodname is not None:
                    name += ":" + v_.funcname.methodname.value.decode('latin1')
                counts[name] = get_token_count(v_.tokens)
            else:
                if isinstance(v_, parser.StatAssignment):
                    var = v_.varlist.vars[0]
                    if hasattr(var, 'name'):
                        varname = v_.varlist.vars[0].name.value.decode('latin1')
                        exp = v_.explist.exps[0].value

                        count = get_token_count(v_.tokens)

                        if isinstance(exp, parser.FunctionCall) and isinstance(exp.exp_prefix, parser.VarName):
                            fname = exp.exp_prefix.name.value.decode('latin1')
                            if fname == 'class' or fname == 'subclass':
                                counts[varname + ':constructor'] = get_token_count(v_.tokens)
                                continue

                counts['global'] = counts.get('global', 0) + get_token_count(v_.tokens)


    else:
        print(v)

    counts = [(k, counts[k]) for k in sorted(counts, key=counts.get, reverse=True)]
    total = 0
    for k, v in counts:
        total += v
        print("{}: {}".format(k, v))

    print("-----")
    print("total: {}".format(total))


def main(orig_args):
    arg_parser = _get_argparser()
    args = arg_parser.parse_args(args=orig_args)

    if args.infile.endswith('.p8'):
        basename = args.infile[:-len('.p8')]
    elif args.infile.endswith('.p8.png'):
        basename = args.infile[:-len('.p8.png')]
    else:
        util.error('Filename {} must end in .p8 or '
                   '.p8.png\n'.format(args.infile))
        return 1

    g = game.Game.from_filename(args.infile)

    # print_token_counts(g.lua.root.stats, {})

    tree = UsageGraphWalker(g.lua.tokens, g.lua.root)
    try:
        it = tree.walk()
        while True:
            it.__next__()
    except StopIteration:
        pass

    return 0


if __name__ == '__main__':
    import sys

    main(sys.argv[1:])
