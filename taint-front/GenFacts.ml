module Env = struct
  module StringSet = Set.Make (String)
  type t = StringSet.t

  let empty = StringSet.empty

  let is_method name t = StringSet.mem name t

  let register_function name t = StringSet.add name t
end

type state = {
  env: Env.t;
  assign: Format.formatter;
  assign_ch: out_channel;
  assign_function: Format.formatter;
  assign_function_ch: out_channel;
  call: Format.formatter;
  call_ch: out_channel;
  indirect_call: Format.formatter;
  indirect_call_ch: out_channel;
  meth: Format.formatter;
  meth_ch: out_channel;
  formal: Format.formatter;
  formal_ch: out_channel;
  actual: Format.formatter;
  actual_ch: out_channel;
  global: Format.formatter;
  global_ch: out_channel;
  taint_spec: Format.formatter;
  taint_spec_ch: out_channel;
  language: Format.formatter;
  language_ch: out_channel;
}

let create fact_dir =
  let env = Env.empty in
  let assign_ch = open_out (Filename.concat fact_dir "Assign.facts") in
  let assign = Format.formatter_of_out_channel assign_ch in
  let assign_function_ch = open_out (Filename.concat fact_dir "AssignFunction.facts") in
  let assign_function = Format.formatter_of_out_channel assign_function_ch in
  let call_ch = open_out (Filename.concat fact_dir "DirectCall.facts") in
  let call = Format.formatter_of_out_channel call_ch in
  let indirect_call_ch = open_out (Filename.concat fact_dir "IndirectCall.facts") in
  let indirect_call = Format.formatter_of_out_channel indirect_call_ch in
  let meth_ch = open_out (Filename.concat fact_dir "Function.facts") in
  let meth = Format.formatter_of_out_channel meth_ch in
  let formal_ch = open_out (Filename.concat fact_dir "FormalParam.facts") in
  let formal = Format.formatter_of_out_channel formal_ch in
  let actual_ch = open_out (Filename.concat fact_dir "ActualParam.facts") in
  let actual = Format.formatter_of_out_channel actual_ch in
  let global_ch = open_out (Filename.concat fact_dir "Global.facts") in
  let global = Format.formatter_of_out_channel global_ch in
  let taint_spec_ch = open_out (Filename.concat fact_dir "TaintSpec.facts") in
  let taint_spec = Format.formatter_of_out_channel taint_spec_ch in
  let language_ch = open_out (Filename.concat fact_dir "CTADLLanguage.facts") in
  let language = Format.formatter_of_out_channel language_ch in
  {
    env;
    assign;
    assign_function;
    call;
    indirect_call;
    meth;
    formal;
    actual;
    global;
    taint_spec;
    language;
    assign_ch;
    assign_function_ch;
    call_ch;
    indirect_call_ch;
    meth_ch;
    formal_ch;
    actual_ch;
    global_ch;
    taint_spec_ch;
    language_ch;
  }


let close state =
  Format.pp_print_flush state.assign ();
  Format.pp_print_flush state.assign_function ();
  Format.pp_print_flush state.call ();
  Format.pp_print_flush state.indirect_call ();
  Format.pp_print_flush state.meth ();
  Format.pp_print_flush state.formal ();
  Format.pp_print_flush state.actual ();
  Format.pp_print_flush state.global ();
  Format.pp_print_flush state.taint_spec ();
  Format.pp_print_flush state.language ();
  close_out state.assign_ch;
  close_out state.assign_function_ch;
  close_out state.call_ch;
  close_out state.indirect_call_ch;
  close_out state.meth_ch;
  close_out state.formal_ch;
  close_out state.actual_ch;
  close_out state.global_ch;
  close_out state.taint_spec_ch;
  close_out state.language_ch

let rec pp_p ff = function
  | Syntax.Array aps ->
    Format.fprintf ff "[%a]" pp_aps aps
  | Syntax.Field (fld, collapse) ->
    Format.fprintf ff ".%s%s" fld (if collapse then ".*" else "")

and pp_path ff = function
  | [] -> Format.fprintf ff ""
  | hd::tl ->
    Format.fprintf ff "%a%a"
      pp_p hd
      pp_path tl

and pp_aps ff = function
  | [] -> Format.fprintf ff "nil"
  | hd::tl ->
    Format.fprintf ff "%a%a"
      pp_ap hd
      pp_aps tl

and pp_ap ff (base, path) =
  Format.fprintf ff "%s\t%a" base pp_path path

let add_assign state lhs rhs fn id =
    Format.fprintf state.assign "%a\t%a\t%s\t%d@."
    pp_ap lhs
    pp_ap rhs
    fn
    id

let add_assign_function state lhs name fn id =
  Format.fprintf state.assign_function "%a\t%s\t%s\t%d@."
    pp_ap lhs
    name
    fn
    id

let add_call state methodname inmeth callid =
  Format.fprintf state.call "%s\t[%d,%s]@."
    methodname
    callid
    inmeth

let add_indirect_call state methodap inmeth callid =
  Format.fprintf state.indirect_call "%a\t[%d,%s]@."
    pp_ap methodap
    callid
    inmeth

let add_call_actuals state num ap inmeth callid =
  Format.fprintf state.actual "%d\t%a\t[%d,%s]@."
    num
    pp_ap ap
    callid
    inmeth

let add_retassign state num dstap inmeth callid =
  Format.fprintf state.actual "%d\t%a\t[%d,%s]@."
    num
    pp_ap dstap
    callid
    inmeth

let add_function_param state name paramnum paramname =
  Format.fprintf state.formal "%d\t%s\t%s@."
    paramnum
    name
    paramname

let add_function state name arity =
  Format.fprintf state.meth "%s\t%d@."
    name
    arity

let add_global state i name =
  Format.fprintf state.global "%s\t%d@." name i

let add_taintspec state ty tag var inmeth id =
  match ty with
  | "source" | "sink" ->
      Format.fprintf state.taint_spec "%s\t%a\t%s\t%s\t%d\t\t@."
        ty
        pp_ap var
        tag
        inmeth
        id
  | _ -> failwith "Invalid taintspec"

let add_sanitizespec state tag ret var inmeth id =
  Format.fprintf state.taint_spec "%s\t%a\t%s\t%s\t%d\t%a@."
    "sanitize"
    pp_ap ret
    tag
    inmeth
    id
    pp_ap var;
  add_assign state ret var inmeth id

let process_stmt state inmeth id (stmt: Syntax.stmt) =
  match stmt with
  | Assign (lhs, (name, [])) when Env.is_method name state.env ->
    add_assign_function state lhs name inmeth id
  | Assign (lhs, rhs) ->
    add_assign state lhs rhs inmeth id
  | Call (Some ret, ("source", []), [(label, [])]) ->
    add_taintspec state "source" label ret inmeth id
  | Call (Some ret, ("sanitize", []), [var; (label, [])]) ->
    add_sanitizespec state label ret var inmeth id
  | Call (_, ("source", []), _) ->
    failwith "Invalid 'source' -- expected res = source(label)"
  | Call (None, ("sink", []), [var; (label, [])]) ->
    add_taintspec state "sink" label var inmeth id
  | Call (_, ("sink", []), _) ->
    failwith "Invalid 'sink' -- expected sink(ap, label)"
  | Call (ret, fn, actuals) ->
    begin match fn with
    | (name, []) when Env.is_method name state.env ->
      add_call state name inmeth id
    | _ ->
      add_indirect_call state fn inmeth id
    end;
    List.iteri (fun i actual ->
        add_call_actuals state i actual inmeth id
      ) actuals;
    begin match ret with
      | Some dstap ->
        add_call_actuals state (-1) dstap inmeth id
      | None ->
        ()
    end
  | Return ap ->
    add_assign state ("<ret>", []) ap inmeth id

let process_fn state (fn : Syntax.fn) =
  add_function state fn.name (List.length fn.formals + 1);
  List.iteri (fun i formal ->
      add_function_param state fn.name i formal
    ) fn.formals;
  add_function_param state fn.name (-1) "<ret>";
  List.iteri (fun i stmt ->
      process_stmt state fn.name i stmt
    ) fn.body

let register_fn env (fn : Syntax.fn ) =
  Env.register_function fn.name env

let process_global state i (global : Syntax.global) =
  add_global state i global.global_name

let process_fns state fns =
  let env = List.fold_left register_fn state.env fns in
  let state = {state with env} in
  List.iter (process_fn state) fns

let process_defs state defs =
  let fns = List.filter_map (fun def ->
      match def with
      | Syntax.Fn fn -> Some fn
      | _  -> None) defs
  in
  let globals = List.filter_map (fun def ->
      match def with
      | Syntax.Global g -> Some g
      | _ -> None) defs
  in
  List.iteri (process_global state) globals;
  process_fns state fns

let process outdir (t : Syntax.t) =
  (* let umask = Unix.umask 0 in *)
  (* ignore (Unix.umask umask); *)
  begin try
      Unix.mkdir outdir 0o755;
    with Unix.Unix_error (Unix.EEXIST, "mkdir", _) ->
      ()
  end;
  let state = create outdir in
  Format.fprintf state.language "taint-front@.";
  process_defs state t;
  close state



