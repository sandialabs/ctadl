{
open Parse

let kw = function
  | "def" -> KWDEF
  | "var" -> KWGLOBAL
  | "return" -> KWRETURN
  | ident -> IDENT ident
}

rule token = parse
| [' ' '\t']+ { token lexbuf }
| ("\r" | "\n" | "\r\n") { Lexing.new_line lexbuf; token lexbuf }
| "//" [^ '\r' '\n']* { token lexbuf }
| ['a'-'z' 'A'-'Z' '_']['a'-'z' 'A'-'Z' '_' '0'-'9']* as ident { kw ident }
| "*" { STAR }
| "," { COMMA }
| "(" { LPAREN }
| ")" { RPAREN }
| "{" { LCURLY }
| "}" { RCURLY }
| "[" { LSQUARE }
| "]" { RSQUARE }
| "." { DOT }
| "=" { ASSIGN }
| ";" { SEMI }
| eof { EOF }
| _ { raise Error }
