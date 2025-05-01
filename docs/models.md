# Models in CTADL

Our format heavily draws from [Mariana Trench](https://mariana-tren.ch/docs/models/#model-generators) (MT) and some of the description below is cribbed from theirs.
If it's reproduced here it's because we support it.
We have features that MT does not support and vice versa.

## Specification

Each JSON file is a JSON object with a key `model_generators` associated with a list of "rules".

Each "rule" defines a "filter" (which uses "constraints" to specify methods for which a "model" should be generated) and a "model". A rule has the following key/values:

- `find`: The type of thing to find. We support `methods`, `variables`, `fields`, and `instructions`;
- `where`: A list of "constraints". All constraints **must be satisfied** by a method or field in order to generate a model for it. All the constraints are listed below, grouped by the type of object they are applied to:

  - **Method**:

    - `signature_match`: Expects at least one of the two allowed groups of extra properties: `[name | names] [parent | parents | extends [include_self]]` where:
      - `name` (a single string) or `names` (a list of alternative strings): is exact matched to the method name
      - `parent` (a single string) or `parents` (a list of alternative strings) is exact matched to the class of the method or `extends` (either a single string or a list of alternative strings) is exact matched to the base classes or interfaces of the method. `extends` allows an optional property `include_self` which is a boolean to indicate if the constraint is applied to the class itself or not (defaults to `true`).
      - `unqualified-id`: a string that is exact matched to the complete ID of the function to match against; this format is dumped when using `ctadl inspect --dump-source-sink-models`
    - `signature | signature_pattern`: Expects an extra property `pattern` which is a regex (with appropriate escaping) to fully match the full signature (class, method, argument types) of a method. Note: this is expensive to evaluate because each signature needs to be compared against each pattern. If there are lots of patterns and lots of functions, the slowdown is noticeable;
    - `parent`: Expects an extra property `inner` [Type] which contains a nested constraint to apply to the class holding the method;
    - `parameter`: Expects an extra properties `idx` and `inner` [Parameter] or [Type], matches when the idx-th parameter of the function or method matches the nested constraint inner;
    - `any_parameter`: Expects an optional extra property `start_idx` and `inner` [Parameter] or [Type], matches when there is any parameters (starting at start_idx) of the function or method matches the nested constraint inner;
    - `has_code`: Accepts an extra property `value` which is either `true` or `false`. By default, `value` is considered `true`;
    - `number_parameters`: Expects an extra property `inner` [Integer] which contains a nested constraint to apply to the number of parameters (counting the implicit `this` parameter);
    - `name`: Expects an extra property `pattern` which is a regex to fully match the name of the item

  - **Variable:**

    - `signature_match`: Expects at least one of the two allowed groups of extra properties: `[name | names] [parent | parents | extends [include_self]]` where:
      - `name` (a single string) or `names` (a list of alternative strings): is exact matched to the variable name
      - `parent` (a single string) or `parents` (a list of alternative strings) is exact matched to the function containing the variable
    - `signature | signature_pattern`: Expects an extra property `pattern` which is a regex (with appropriate escaping) to fully match the variable name;
    - `parent`: Expects an extra property `inner` [Type] which contains a nested constraint to apply to the function containing the variable;
    - `name`: Expects an extra property `pattern` which is a regex to fully match the name of the item

  - **Instruction:**

    - `uses_field`: Matches on instructions that use fields. Expects one of the extra properties: `[name | names] | unqualified-id` where:
      - `name` (a single string) or `names` (a list of alternative strings) is exact matched to the unadorned field name
      - `unqualified-id` (a single string) is matched to the fully-qualified field ID, which is language-specifid

  - **Integer:**

    - `< | <= | == | > | >= | !=`: Expects an extra property `value` which contains an integer that the input integer is compared with. The input is the left hand side.

  - **Any (Method, Parameter, Type, Field or Integer):**
    - `all_of`: Expects an extra property `inners` [Any] which is an array holding nested constraints which must all apply;
    - `any_of`: Expects an extra property `inners` [Any] which is an array holding nested constraints where one of them must apply;
    - `not`: Expects an extra property `inner` [Any] which contains a nested constraint that should not apply. (Note this is not yet implemented for `Field`s)

- `model`: A model, describing sources/sinks/propagations/etc.

  - **For method models**
    - `sources`: A list of sources, i.e a source *flowing out* of the method via return value or *flowing in* via an argument. To specify sources *flowing out* via an argument, specify it as `generations`. A source/generation has the following key/values:
      - `kind`: The source name;
      - `port`: The source access path (e.g, `"Return"` or `"Argument(1)"`);
    - `sinks`: A list of sinks, i.e describing that a parameter of the method flows into a sink. A sink has the following key/values:
      - `kind`: The sink name;
      - `port`: The sink access path (e.g, `"Return"` or `"Argument(1)"`);
    - `propagation`\*: A list of propagations (also called passthrough) that describe whether a taint on a parameter should result in a taint on the return value or another parameter. A propagation has the following key/values:
      - `input`: The input access path (e.g, `"Argument(1)"`);
      - `output`: The output access path (e.g, `"Return"` or `"Argument(2)"`);
    - `forward_self`: A where constraint that matches against methods. This models the scenario where calls to a method A on an object O should should be forwarded to method B on object O. An example is handling `execute` in [AsyncTask](https://developer.android.com/reference/android/os/AsyncTask#execute%2528java.lang.Runnable%2529) by forwarding it to `doInBackground`
      - `where`: a list of constraint matching methods
  - **For taint models**
    - A `taint` model is used for the `ctadl match` subcommand, which allows one to write simple match querios to match against an index.
    - `kind`: Label for a taint model

Note, the implicit `this` parameter for methods has the parameter number 0.

## Access path format

An access path describes the symbolic location of a taint. This is commonly used to indicate where a source or a sink originates from. The "port" field of any model is represented by an access path.

An access path is composed of a root and a path.

The root is either:

- `Return`, representing the returned value;
- `Argument(x)` (where `x` is an integer), representing the parameter number `x`. **Note** that `Argument(0)` represents the implicit `this` parameter for instance methods;

The path is a (possibly empty) list of path elements. A path element can be any of the following kinds:

- `field`: represents a field name. String encoding is a dot followed by the field name: `.field_name`;
- `index`: represents a user defined index for arrays. String encoding uses square braces to enclose an integer: `[3]`;
- `any field or subfield`: represents any sequence of subsequente field names. `.field_name.*` or simply `.*`

Examples:

- `Argument(1).name` corresponds to the _field_ `name` of the second parameter;
- `Argument(1).*` corresponds to _any access inside_ the second parameter;
- `Return` corresponds to the returned value;
- `Return.x` corresponds to the field `x` of the returned value;

> **NOTE 1:** Instance (i.e, non-static) method parameters are indexed starting from 1! The 0th parameter is the `this` parameter in Dalvik byte-code. For static method parameters, indices start from 0.

> **NOTE 2:** In a constructor (`<init>` method), parameters are also indexed starting from 1. The 0th parameter refers to the instance being constructed, similar to the `this` reference.
