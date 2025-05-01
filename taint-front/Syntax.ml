type p =
  | Array of ap list
  (* field + collapse. if collapse is true, field is empty *)
  | Field of (string * bool)

and ap = string * p list

let rec pp_p ff = function
  | Array aps ->
    Format.fprintf ff "[%a]"
      (Format.pp_print_list ~pp_sep:(fun ff () -> Format.pp_print_string ff ", ") pp_ap) aps
  | Field (fld, collapse) ->
    Format.fprintf ff ".%s%s" fld (if collapse then "*" else "")


and pp_ap ff (base, path) =
    Format.fprintf ff "%s" base;
    List.iter (fun p ->
        Format.fprintf ff "%a" pp_p p
      ) path

type stmt =
  | Assign of ap * ap
  | Call of ap option * ap * ap list
  | Return of ap

let pp_stmt ff = function
  | Assign (lhs, rhs) ->
    Format.fprintf ff "%a = %a;"
      pp_ap lhs
      pp_ap rhs
  | Call (None, fn, actuals) ->
    Format.fprintf ff "%a(%a);"
      pp_ap fn
      (Format.pp_print_list ~pp_sep:(fun ff () -> Format.pp_print_string ff ", ") pp_ap) actuals
  | Call (Some lhs, fn, actuals) ->
    Format.fprintf ff "%a = %a(%a);"
      pp_ap lhs
      pp_ap fn
      (Format.pp_print_list ~pp_sep:(fun ff () -> Format.pp_print_string ff ", ") pp_ap) actuals
  | Return ap ->
    Format.fprintf ff "return %a;" pp_ap ap

type fn = {
  name: string;
  formals: string list;
  body: stmt list;
}

let pp_fn ff fn =
  Format.fprintf ff "@[<v 0>@[<v 2>def %s(%a) {"
    fn.name
    (Format.pp_print_list ~pp_sep:(fun ff () -> Format.pp_print_string ff ", ") Format.pp_print_string) fn.formals;
  List.iter (fun stmt ->
      Format.fprintf ff "@,%a" pp_stmt stmt
    ) fn.body;
  Format.fprintf ff "@]@,}@]"

type global = {
  global_name: string;
}

let pp_global ff global =
    Format.fprintf ff "global %s;@." global.global_name

type def = Global of global | Fn of fn

let pp_def ff def =
    match def with
    | Global g -> pp_global ff g
    | Fn fn -> pp_fn ff fn

type t = def list

let pp ff fns =
  Format.fprintf ff "@[<v 0>";
  List.iter (fun def ->
      Format.fprintf ff "%a@," pp_def def
    ) fns;
  Format.fprintf ff "@]"



