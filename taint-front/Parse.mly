%token KWDEF "def"
%token KWGLOBAL "var"
%token KWRETURN "return"
%token <string> IDENT
%token COMMA ","
%token LPAREN "("
%token RPAREN ")"
%token LCURLY "{"
%token RCURLY "}"
%token LSQUARE "["
%token RSQUARE "]"
%token DOT "."
%token ASSIGN "="
%token SEMI ";"
%token STAR "*"
%token EOF

%type <Syntax.t> top
%{
    exception Error
%}
%start top
%%

top: defs=list(def) EOF { defs } ;

def:
  "var" global_name=IDENT ";" {
    Syntax.(Global { global_name })
  }
| "def" name=IDENT "(" formals=separated_list(",", IDENT) ")" "{" body=list(stmt) "}" {
    Syntax.(Fn { name; formals; body })
  }
;

p:
| "[" aps=separated_list(",", ap) "]" { Syntax.Array aps }
| "." fld=IDENT { Syntax.Field (fld, false) }
| "." STAR { Syntax.Field ("", true) }
;

ap:
| base=IDENT path=list(p)
  { (base, path) }
;

stmt:
| lhs=ap "=" rhs=ap ";"
    { Syntax.Assign (lhs, rhs) }
| lhs=ap "=" fn=ap "(" actuals=separated_list(",", ap) ")" ";"
    { Syntax.Call (Some lhs, fn, actuals) }
| fn=ap "(" actuals=separated_list(",", ap) ")" ";"
    { Syntax.Call (None, fn, actuals) }
| "return" expr=ap ";"
    { Syntax.Return expr }
;



