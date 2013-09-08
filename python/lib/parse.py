import re

from parsimonious import Grammar
from parsimonious.nodes import NodeVisitor


CHARSET = re.compile(r'@charset[\s]*(.+?)[\s]*;')

# Adapted from https://raw.github.com/bhyde/css-parser/master/css.peg:
# This is an incredibly inefficient grammar, but it would be simple to
# optimize. Eventually, Parsimonious will know how to do that automatically.
css = Grammar(ur"""
    program = S* stylesheet
    stylesheet = ("@charset" S* STRING S* ";")? SCC (import SCC)* (namespace SCC)* ((ruleset / media / page / font_face / keyframes) SCC)*
    SCC = S / CDO / CDC
    import = "@import" S* (STRING / URI) S* medium_list? ";" S*
    namespace = "@namespace" S* (IDENT S*)? (STRING / URI) S* ";" S*
    media = "@media" medium_list "{" (ruleset / media)* "}" S*
    medium_list = S* media_query ("," S* media_query)*
    media_query = media_query_type / media_query_expr
    media_query_type = ("only" / "not")? S* IDENT S* ("and" S* media_query_expr)?
    media_query_expr = media_expr ("and" S* media_expr)*
    media_expr = "(" S* IDENT S* (":" S* expr)? ")" S*
    page = "@page" S* IDENT? pseudo_page? S* "{" S* declaration_list? "}" S*
    pseudo_page = ":" IDENT
    font_face = "@font-face" S* "{" S* declaration_list? "}" S*
    keyframes = "@" vendor_prefix? "keyframes" S* IDENT S* "{" S* keyframe+ "}" S*
    keyframe = keyframe_selector_list "{" S* declaration_list "}" S*
    keyframe_selector_list = keyframe_selector S* ("," S* keyframe_selector S*)*
    keyframe_selector = (num "%") / "from" / "to"
    combinator = ("+" / ">" / "~") S*
    unary_operator = "-" / "+"
    ruleset = more_selector S* "{" S* declaration_list? "}" S*
    more_selector = selector (S* "," S* selector)*

    vendor_prefix = ~r"\-[a-zA-Z]+\-"

    h = ~r"[0-9a-fA-F]"
    nonascii = ~u"[\u0080-\ud7ff\ue000-\ufffd\u10000-\u10ffff]"
    unicode = ~r"\\[0-9a-fA-F]{1,6}[ \n\r\t\f]"
    escape = unicode / ~u"\\[\u0020-\u007E\u0080-\uD7FF\uE000-\uFFFD\u10000-\u10FFFF]"
    nmstart = ~r"-?[a-zA-Z_]" #/ escape #/ nonascii
    nmchar = ~r"[a-zA-Z0-9\-_]" #/ escape #/ nonascii
    string_chars = ~r"[\t \!#\$%&\(-~]" / ~r"\\(\n|\r\n|\r|\f)" / nonascii #/ escape
    string1 = "\"" ("\'" / string_chars)* "\""
    string2 = "\'" ("\"" / string_chars)* "\'"
    urlchar = ~r"[\t!-\'*-~]" / nonascii #/ escape

    IDENT = nmstart nmchar*
    name = nmchar+
    num = unary_operator? ~r"([0-9]*\.[0-9]+|[0-9]+)"
    STRING = string1 / string2
    url = urlchar+
    w = ~r"[ \n\r\t\f]*"

    comment = ~r"\/\*[^*]*\*+([^/*][^*]*\*+)*\/"
    S = w / comment

    CDO = "<!--"
    CDC = "-->"

    HASH = "#" name

    IMPORTANT_SYM = "!" w "important"

    dim_unit = IDENT / "%"
    DIMENSION = num dim_unit

    URI = "url(" w (STRING / url) w ")"

    selector = simple_selector selector_trailer?
    selector_trailer = S* (combinator? selector)?

    simple_selector = (element_name simple_selector_etc*) / (simple_selector_etc+)
    simple_selector_etc = id_selector / class_selector / attrib_selector / pseudo_selector

    element_type = IDENT / "*"
    element_ns = "|" IDENT
    element_name = (element_type element_ns?) / element_ns

    id_selector     = "#" IDENT
    class_selector  = "." IDENT
    attrib_selector = "[" S* IDENT ( ("=" / "~=" / "|=" / "^=" / "$=" / "*=") S* ( IDENT / STRING ) S*)? "]"
    pseudo_selector = ":" (pseudo_sel_elem / pseudo_sel_nth / pseudo_sel_not / pseudo_sel_func / IDENT)
    nth_func = "nth-child" / "nth-last-child" / "nth-of-type" / "nth-last-of-type"
    pseudo_sel_elem = ":" IDENT
    pseudo_sel_nth = nth_func "(" S* nth S* ")"
    pseudo_sel_not = "not(" S* more_selector S* ")"
    pseudo_sel_func = IDENT "(" S* expr ")"

    integer = ~r"[1-9][0-9]*"
    nth = nth_body_full / nth_body_num / "odd" / "even"
    nth_body_full = unary_operator? integer? "n" (S* unary_operator S* integer)?
    nth_body_num = unary_operator? integer

    declaration_list = declaration (";" S* declaration)* ";"? S*
    declaration = (filter_property / normal_property) S* (IMPORTANT_SYM S*)?
    property = IDENT S*
    normal_property = property ":" S* expr
    filter_property = "filter:" S* ie_filter_blob
    expr_operator = "/" / ","
    expr = term S* (expr_operator? S* term)*
    math_expr = math_product (S+ ("+" / "-") S+ math_product)*
    math_product = unit (S* (("*" S* unit) / ("/" S* num)))*
    calc = "calc(" S* math_expr S* ")"
    attr = "attr(" S* element_name (S+ IDENT)? S* ("," (unit / calc) S*)? ")"
    paren_math_expr = "(" S* math_expr S* ")"  # XXX: Is this needed?
    unit = DIMENSION / num / paren_math_expr / calc / attr / function
    term = (URI / unit / STRING / IDENT / hexcolor) S*

    ie_filter_blob = ie_filter_blob_term (S+ ie_filter_blob)? S*
    ie_filter_blob_term = ~r"(progid:)?[a-zA-Z0-9\.]+\([a-zA-Z0-9=#, \n\r\t]*\)"

    function = IDENT "(" S* expr ")" S*
    hexcolor = ("#" h h h h h h) / ("#" h h h)

    """)


import declaration
import media
import objects
import selector
from rule import (RuleAttribute, RuleClass, RuleID, RulePseudoClass, RuleType)
from statement import (FontFace, Keyframe, Keyframes, KeyframeSelector,
                       MediaQuery, Statement)
from stylesheet import Stylesheet


class CssVisitor(NodeVisitor):
    def visit_program(self, node, body):
        return body[-1]

    def visit_stylesheet(self, node, body):
        sheet = Stylesheet()

        charset = body[0]
        if charset:
            sheet.charset = body[0][0][2]

        imports = body[2]
        for imp in imports:
            imp_val = imp[0][2]
            imp_media = imp[0][4]
            # TODO: assign these

        namespaces = body[3]
        for ns in namespaces:
            ns_name = ns[0][2]
            ns_ns = ns[0][3][0]
            if not ns_name:
                sheet.default_namespace = ns_ns
                continue
            sheet.namespaces[ns_name] = ns_ns

        statements = body[4]
        for stmt in statements:
            sheet.statements.append(stmt[0][0])
        return sheet

    def visit_import(self, node, body):
        return body[2], body[4][0] if body[4] else None

    def visit_media(self, node, body):
        medium_list = body[1]
        media = MediaQuery(medium_list)

        for stmt in body[3]:
            media.statements.append(stmt[0])

        return media

    def visit_medium_list(self, node, body):
        output = [body[1]]
        if body[2]:
            for query in body[2]:
                output.append(query[2])

        return output

    def visit_media_query(self, node, body):
        result = body[0]
        if isinstance(result, list):
            return media.MediaQuery(media_exprs=result)
        return result

    def visit_media_query_type(self, node, body):
        exprs = body[4]
        return media.MediaQuery(
                media_type=body[2],
                media_type_modifier=body[0][0][0] if body[0] and body[0][0][0] else None,
                media_exprs=exprs[0][2] if exprs else None)

    def visit_media_query_expr(self, rule, body):
        output = [body[0]]
        if body[1]:
            for expr in body[1]:
                output.append(expr[2])
        return output

    def visit_media_expr(self, rule, body):
        return media.MediaExpr(body[2], body[4][0][2] if body[4] else None)

    def visit_font_face(self, node, body):
        descriptors = body[4][0]
        return FontFace(descriptors)

    def visit_keyframes(self, node, body):
        return Keyframes(name=body[4],
                         frames=body[8],
                         prefix=body[1][0] if body[1] else None)

    def visit_keyframe(self, node, body):
        selectors = body[0]
        descriptors = body[3] or []
        return Keyframe(selectors, descriptors)

    def visit_keyframe_selector_list(self, node, body):
        output = [body[0]]
        if body[2]:
            for frame in body[2]:
                output.append(frame[2])

        return output

    def visit_keyframe_selector(self, node, body):
        sel = body[0]
        if not sel:
            return KeyframeSelector(node.text)
        return KeyframeSelector(sel[0])  # Return numeric part of percent.

    def visit_vendor_prefix(self, node, body):
        return node.text

    def visit_ruleset(self, rule, body):
        return Statement(body[0], body[4][0] if body[4] else [])

    def visit_more_selector(self, node, body):
        sels = [body[0]]
        for sel in body[1]:
            sels.append(sel[-1])
        return selector.MultiSelector(sels)

    def visit_selector(self, node, body):
        ssel = body[0]
        if not body[1][0]:
            return ssel
        combinator, subsel = body[1][0]

        if not combinator:
            return selector.DescendantSelector(ssel, subsel)
        elif combinator == '+':
            return selector.AdjacencySelector(ssel, subsel)
        elif combinator == '>':
            return selector.DirectDescendantSelector(ssel, subsel)
        elif combinator == '~':
            return selector.SiblingSelector(ssel, subsel)

        raise Exception('Unrecognized selector')

    def visit_combinator(self, node, (op, ws)):
        return node.text.strip()

    def visit_selector_trailer(self, node, (ws, body)):
        if not body:
            return None
        combinator, subsel = body[0]
        return combinator[0] if combinator else None, subsel

    def visit_simple_selector(self, ssel, body):
        ss = selector.SimpleSelector()
        body = body[0]
        if isinstance(body[0], RuleType):
            ss.rules.append(body[0])
            if len(body) == 1:
                return ss
            body = body[1]
        for rule in body:
            ss.rules.append(rule)
        return ss

    def visit_element_name(self, node, body):
        return RuleType(node.text)

    def visit_simple_selector_etc(self, node, body):
        return body[0]

    def visit_id_selector(self, node, (_, name)):
        return RuleID(name)

    def visit_class_selector(self, node, (_, name)):
        return RuleClass(name)

    def visit_pseudo_selector(self, node, (_, sel)):
        obj = sel[0]
        if isinstance(obj, (str, unicode)):
            return RulePseudoClass(obj)
        return obj

    def visit_pseudo_sel_elem(self, node, (_, ident)):
        return RulePseudoClass(ident)

    def visit_pseudo_sel_nth(self, node, body):
        return RulePseudoClass(body[0], body[3])

    def visit_pseudo_sel_not(self, node, body):
        return RulePseudoClass('not', body[2])

    def visit_pseudo_sel_func(self, node, body):
        return RulePseudoClass(body[0], body[3])

    def visit_nth(self, node, body):
        if not body[0]:
            return node.text
        return body[0]

    def visit_nth_func(self, node, body):
        return node.text

    def visit_nth_body_full(self, node, body):
        coef = body[1][0] if body[1] else objects.Number('1')
        if body[0]:
            coef.apply_unary(body[0][0])

        offset = None
        if body[3]:
            offset = body[3][0][3]
            offset_uop = body[3][0][1]
            if offset_uop:
                offset.apply_unary(offset_uop)

        return objects.LinearFunc(coef, offset)

    def visit_nth_body_num(self, node, body):
        offset = body[1]
        if body[0]:
            offset.apply_unary(body[0][0])
        return objects.LinearFunc(None, offset)

    def visit_unary_operator(self, node, body):
        return node.text

    def visit_attrib_selector(self, node, body):
        binop, val = None, None
        if body[3]:
            binop = node.children[3].children[0].children[0].text
            val = body[3][0][2][0]
        return RuleAttribute(body[2], binop, val)

    def visit_declaration_list(self, node, body):
        decls = [body[0]]
        if body[1]:
            for decl in body[1]:
                decls.append(decl[2])
        return decls

    def visit_declaration(self, node, body):
        decl = body[0][0]
        decl.imp = bool(body[2][0] if body[2] else None)
        return decl
        
    def visit_normal_property(self, node, body):
        return declaration.Declaration(body[0][0], body[3])
        
    def visit_filter_property(self, node, body):
        return declaration.Declaration(u'filter', body[2])

    def visit_expr_operator(self, node, body):
        return node.text

    def visit_expr(self, node, body):
        extra_terms = []
        for op, _, term in body[2]:
            extra_terms.append((op[0] if op else None, term))

        return declaration.Expression(body[0], extra_terms)

    def visit_term(self, node, body):
        return body[0][0]

    def visit_unit(self, node, (content, )):
        return content

    def visit_paren_math_expr(self, node, body):
        return body[2]

    def visit_STRING(self, node, body):
        # XXX: objects.String(node.text[1:-1]) would be better?
        return objects.String(u''.join(x[0] for x in body[0][1]))

    def visit_url(self, node, body):
        return node.text

    def visit_URI(self, node, body):
        return objects.URI(body[2][0])

    def visit_num(self, node, body):
        return objects.Number(node.text)

    def visit_integer(self, node, body):
        return objects.Number(node.text)

    def visit_function(self, node, body):
        return declaration.Function(body[0], body[3])

    def visit_string_chars(self, node, body):
        return node.text

    def visit_dim_unit(self, node, body):
        return node.text

    def visit_DIMENSION(self, node, body):
        return objects.Dimension(body[0], body[1])

    def visit_hexcolor(self, node, body):
        return objects.Color.fromhex(node.text)

    def visit_IDENT(self, node, _):
        return node.text

    def visit_ie_filter_blob(self, node, body):
        return node.text

    def visit_S(self, *args):
        return None

    def visit_SCC(self, *args):
        return None

    def generic_visit(self, node, visited_children):
        return visited_children


if __name__ == '__main__':
    tree = css.parse("""
        p #id:nth-child(-3n + 4) .class p.classname#identifier {
            thing: 4em !important;
            thang: 5khz
        }
        """)

    print tree
    visited = CssVisitor().visit(tree)
    print unicode(visited)
    print visited.pretty()
    import pdb; pdb.set_trace()

def do_parse(raw):
    # Try to decode the string if it's encoded.
    if not isinstance(raw, unicode):
        charset_match = CHARSET.search(raw)
        charset = 'utf-8'
        if charset_match:
            charset = charset_match.group(1).strip('"\'')
        try:
            raw = raw.decode(charset)
        except Exception:
            pass

    tree = css.parse(raw)
    return CssVisitor().visit(tree)
