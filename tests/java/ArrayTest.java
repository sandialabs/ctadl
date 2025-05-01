package defpackage;

class ArrayTest {
  public static boolean Foo(String a) {
    String[] array = {"hello", "new", "world", a};
    ArrayTest.Bar(array);
    return false;
  }

  public static void Bar(String[] arr) {
  }
}
