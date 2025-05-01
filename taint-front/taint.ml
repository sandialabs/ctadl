open! Taintlang
open! Parse

let _ = 
  let out_dir = ref "facts" in
  let files = ref [] in
  Arg.parse [
    "-o", Arg.Set_string out_dir, "<dir> output directory";
  ] (fun fname ->
      files := fname :: !files
    ) "Sample language for taint analysis";

  let files = List.rev !files in

  let ast = List.filter_map (fun fname ->
      let inch = open_in fname in
      let lexbuf = Lexing.from_channel inch in
      try
        let ast = Parse.top Lex.token lexbuf in
        Some ast
      with Parse.Error ->
        let pos = lexbuf.lex_curr_p in
        Format.printf "Parse error %s(%d:%d)@."
          fname
          pos.Lexing.pos_lnum
          (pos.Lexing.pos_cnum - pos.Lexing.pos_bol);
        None
    ) files |> List.flatten in

  GenFacts.process !out_dir ast
