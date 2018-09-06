import argparse

from pico8 import util
from pico8.game import game
from pico8.lua import lua, parser, lexer


def _get_argparser():
    parser = argparse.ArgumentParser()
    parser.add_argument('infile', type=str,
                        help='the cart to turn upside down; can be .p8 '
                             'or .p8.png')
    return parser


class TokenCountASTWalker(lua.BaseASTWalker):
    """Transforms Lua code to invert coordinates of drawing functions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _walk_FunctionCall(self, node):
        print(node)
        return


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
    for k, v in counts:
        print("{}: {}".format(k, v))


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

    print_token_counts(g.lua.root.stats, {})

    return 0


if __name__ == '__main__':
    import sys

    main(sys.argv[1:])
