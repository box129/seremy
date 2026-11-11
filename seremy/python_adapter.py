"""Python AST declarations and conservative lexical/module call binding."""
import ast
import io
import tokenize
from pathlib import PurePosixPath
from seremy.contracts import Span, sha256_hex
from seremy.parsing import ParsedFileResult, DeclarationRecord, CandidateRecord

METHOD = "python-ast-static-v0.1"


class Extractor(ast.NodeVisitor):
    def __init__(self, file_id, raw):
        self.file_id, self.raw = file_id, raw
        self.text = raw.decode("utf8")
        self.lines = self.text.splitlines(keepends=True)
        self.offsets = [0]
        for line in self.lines:
            self.offsets.append(self.offsets[-1] + len(line.encode()))
        self.scopes = [{"parent": None, "kind":"module", "bindings":{}}]
        self.scope = 0
        self.declarations, self.calls, self.imports = [], [], []
        self.conditional = 0
        self.tokens = list(tokenize.generate_tokens(io.StringIO(self.text).readline))

    def span(self, node):
        return Span(self.offsets[node.lineno-1]+node.col_offset,
                    self.offsets[node.end_lineno-1]+node.end_col_offset)

    def name_span(self, node):
        token = next(t for t in self.tokens if t.start[0] == node.lineno
                     and t.type == tokenize.NAME and t.string == node.name
                     and t.start[1] >= node.col_offset)
        start = self.offsets[token.start[0]-1]+len(self.lines[token.start[0]-1][:token.start[1]].encode())
        return Span(start, start+len(node.name.encode()))

    def bind(self, name, value):
        self.scopes[self.scope]["bindings"].setdefault(name, []).append(value)

    def function(self, node, kind):
        d = DeclarationRecord(kind, node.name, self.name_span(node), self.span(node))
        self.declarations.append(d)
        self.bind(node.name, ("conditional" if self.conditional else "declaration", d))
        for item in node.decorator_list:
            self.visit(item)
        if hasattr(node, "args"):
            for item in node.args.defaults+list(filter(None,node.args.kw_defaults)):
                self.visit(item)
        parent = self.scope
        self.scopes.append({"parent":parent,"kind":"class" if kind=="class_declaration" else "function","bindings":{},"owner":d})
        self.scope = len(self.scopes)-1
        if hasattr(node,"args"):
            args = node.args.posonlyargs+node.args.args+node.args.kwonlyargs
            args += [a for a in [node.args.vararg,node.args.kwarg] if a]
            for arg in args:
                self.bind(arg.arg, ("value",None))
        for item in node.body:
            self.visit(item)
        self.scope = parent

    def visit_FunctionDef(self,node):
        self.function(node,"function_declaration")

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self,node):
        self.function(node,"class_declaration")

    def visit_Name(self,node):
        if isinstance(node.ctx,(ast.Store,ast.Del)):
            self.bind(node.id,("value",None))

    def visit_Global(self,node):
        for name in node.names:
            self.bind(name,("unsupported_scope",None))

    visit_Nonlocal = visit_Global

    def visit_ExceptHandler(self,node):
        if node.name:
            self.bind(node.name,("value",None))
        self.generic_visit(node)

    def visit_Lambda(self,node):
        parent=self.scope
        self.scopes.append({"parent":parent,"kind":"lambda","bindings":{}})
        self.scope=len(self.scopes)-1
        for arg in node.args.posonlyargs+node.args.args+node.args.kwonlyargs:
            self.bind(arg.arg,("value",None))
        self.visit(node.body)
        self.scope=parent

    def visit_Import(self,node):
        for alias in node.names:
            self.bind(alias.asname or alias.name.split(".")[0], ("module",alias.name if alias.asname else alias.name.split(".")[0]))
            self.imports.append((alias,alias.name))

    def visit_MatchAs(self,node):
        if node.name:
            self.bind(node.name,("value",None))
        self.generic_visit(node)

    visit_MatchStar = visit_MatchAs

    def visit_MatchMapping(self,node):
        if node.rest:
            self.bind(node.rest,("value",None))
        self.generic_visit(node)

    def visit_ImportFrom(self,node):
        for alias in node.names:
            self.bind(alias.asname or alias.name,("import",(node.module or "",node.level,alias.name)))
        self.imports.append((node,"."*node.level+(node.module or "")))

    def visit_Call(self,node):
        self.calls.append((node,self.scope))
        self.generic_visit(node)

    def visit_If(self,node):
        self.conditional += 1
        self.generic_visit(node)
        self.conditional -= 1

    visit_Try = visit_If
    visit_For = visit_If
    visit_AsyncFor = visit_If
    visit_While = visit_If
    visit_Match = visit_If


def parse_python(inputs):
    """Inputs contain only snapshot-frozen Python bytes keyed by file ID."""
    modules, results = {}, {}
    context = {"method":METHOD,"snapshot_files":sorted([p,sha256_hex(raw)] for p,raw in inputs.items())}
    for path, raw in sorted(inputs.items()):
        digest = sha256_hex(raw)
        try:
            extractor = Extractor(path,raw)
            tree = ast.parse(extractor.text, filename=path)
            extractor.visit(tree)
            modules[path] = extractor
            results[path] = ParsedFileResult(path,digest,digest,"complete",None,
                extractor.declarations,[],[],0,
                {"profile":METHOD,"constructs":["function","class","import","direct_call"],"dynamic_calls":"unsupported"},None)
        except (SyntaxError,UnicodeError,tokenize.TokenError,IndentationError) as error:
            results[path] = ParsedFileResult(path,digest,digest,"failed","python_parse_error",
                [],[],[{"message":str(error)}],0,{"profile":METHOD},None)

    def module_path(source, name, level=0):
        parts = name.split(".") if name else []
        if level:
            base = list(PurePosixPath(source).parent.parts)
            if level > len(base)+1:
                return None
            parts = base[:len(base)-level+1]+parts
        rel = "/".join(parts)
        return next((p for p in [rel+".py",rel+"/__init__.py"] if p in modules),None)

    def lookup(path, scope, name, seen):
        key = (path,scope,name)
        if key in seen:
            return "unsupported",None
        seen = seen | {key}
        ex = modules[path]
        s = ex.scopes[scope]
        values = s["bindings"].get(name,[])
        if not values:
            parent = s["parent"]
            # Methods do not close over their class namespace.
            while parent is not None and ex.scopes[parent]["kind"]=="class":
                parent = ex.scopes[parent]["parent"]
            return lookup(path,parent,name,seen) if parent is not None else ("missing",None)
        if len(values)!=1:
            return "unsupported",None
        kind,value = values[0]
        if kind=="declaration":
            return kind,(path,value)
        if kind=="import":
            name,level,symbol = value
            target = module_path(path,name,level)
            if target:
                return lookup(target,0,symbol,seen)
            return ("missing" if level else "external"),name
        if kind=="module":
            target=module_path(path,value)
            return ("module",target) if target else ("external",value)
        return "unsupported",None

    for path,ex in modules.items():
        result=results[path]
        for node,name in ex.imports:
            span=ex.span(node)
            result.candidates.append(CandidateRecord("import_specifier",ex.raw[span.start:span.end].decode(),span,{"module_path":name}))
        for node,scope in ex.calls:
            expr=node.func
            if isinstance(expr,ast.Name):
                span=ex.span(expr)
                kind,target=lookup(path,scope,expr.id,set())
            elif isinstance(expr,ast.Attribute) and isinstance(expr.value,ast.Name):
                full=ex.span(expr)
                span=Span(full.end-len(expr.attr.encode()),full.end)
                kind,target=lookup(path,scope,expr.value.id,set())
                kind,target=lookup(target,0,expr.attr,set()) if kind=="module" else ("unsupported",None)
            else:
                span=ex.span(expr)
                kind,target="unsupported",None
            if ex.scopes[scope]["kind"]=="lambda":
                kind,target="unsupported",None
            observation={"context":context}
            if kind=="declaration" and target[1].kind=="function_declaration":
                fid,d=target
                observation.update(outcome="RESOLVED_SINGLE",target={"file_id":fid,"content_sha256":sha256_hex(inputs[fid]),"name":d.name,"kind":d.kind,"name_byte":[d.name_span.start,d.name_span.end]})
            elif kind=="external":
                observation.update(outcome="EXTERNAL",reason="external_module",target=str(target))
            else:
                observation.update(outcome="MISSING" if kind=="missing" else "UNSUPPORTED",reason="unknown_name" if kind=="missing" else "dynamic_or_unsupported_binding")
            owner=ex.scopes[scope].get("owner")
            source_owner=f"ent:{path}#{owner.kind}:{owner.name}@{owner.name_span.start}" if owner else "file:"+path
            result.candidates.append(CandidateRecord("call",ex.raw[span.start:span.end].decode(),span,{"binding":observation,"source_owner":source_owner}))
    return [results[p] for p in sorted(results)]

