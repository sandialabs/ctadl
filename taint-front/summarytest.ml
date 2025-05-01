open! Taintlang
open! Syntax

module Seq = struct
  include Seq

  let mapi f s =
    Seq.unfold (fun (i, s) ->
      let open Seq in
      match s () with
      | Nil -> None
      | Cons (x, rest) -> begin
        let elt = f (i, x) in
        let next = (i+1, rest) in
        Some (elt, next)
      end
    ) (0, s)
end

let f ~num_assigns ~num_calls ?(distinct=false) () =
  let _ = ignore (distinct) in
  let gentup seed ~id =
    Seq.unfold (fun n ->
      match n with
      | 0 -> None
      | _ -> Some (
        let elt = ((Format.asprintf "%s%d" id n, []), (Format.asprintf "%s%d" id (n+1), [])) in
        let next = n-1 in
        (elt, next)
        )
    ) seed
  in
  let _genargs seed ~id =
    Seq.unfold (fun n ->
      match n with
      | 0 -> None
      | _ -> Some (
        let elt = (Format.asprintf "%s%d" id n, Format.asprintf "%s%d" id (n+1)) in
        let next = n-1 in
        (elt, next)
        )
    ) seed
  in
  let genstmt n =
    Seq.map (fun (x,y) -> Assign (x,y)) (gentup ~id:"x" n)
  in
  let gencall n =
    Seq.map (fun (x,y) ->
      (Call (None, ("f1", []), [x; y]))
    ) (gentup ~id:"a" n)
  in
  let gencalls n =
    Seq.mapi (fun (n, (x,y)) ->
      (Call (None, (Format.asprintf "f%d" (n+1), []), [x; y]))
    ) (gentup ~id:"a" n)
  in
  let genfuncs count =
    Seq.unfold (fun n ->
      if n = 0 then None
      else Some (
        let elt = Fn {
          name= Format.asprintf "f%d" n;
          formals= ["x1"; Format.asprintf "x%d" (num_assigns+1)];
          body= List.of_seq @@ genstmt num_assigns;
        }
        in
        let next = n-1 in
        (elt, next)
      )
    ) count
  in
  (List.of_seq @@ genfuncs (if distinct then num_calls else 1)) @
  [
    Fn {
      name= "main";
      formals= [];
      body= List.concat [
          [Call (Some (Format.asprintf "a%d" (num_calls+1), []), ("source", []), [("Network", [])])];
        List.of_seq @@ (if not distinct then gencall else gencalls) num_calls;
        [Call (None, ("sink", []), [("a1", []); ("Network", [])])];
      ];

    };
  ]

let _ =
  let num_assigns = ref 1 in
  let num_calls = ref 1 in
  let distinct = ref false in
  let print = ref false in
  Arg.parse [
    "--num-assigns", Arg.Set_int num_assigns, "<int> number of assignments in f";
    "--num-calls", Arg.Set_int num_calls, "<int> number of calls to f";
    "--distinct", Arg.Set distinct, "<bool> false=all calls to f, else distinct calls";
    "--print", Arg.Set print, "<bool> print ast";
  ] (fun _ -> ())
  "Generate function summarization benchmark";
  let ast =
    let num_assigns = !num_assigns in
    let num_calls = !num_calls in
    let distinct = !distinct in
    f ~num_assigns ~num_calls ~distinct ()
  in
  let out_dir = ref "facts" in
  if !print then Format.printf "%a" pp ast;
  GenFacts.process !out_dir ast
