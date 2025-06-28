// clang-format off
// macos
// ; clang++ --std=c++20 -I $(dirname $(which souffle))/../include -I $(dirname $(which souffle))/../include/souffle src/ctadl/souffle-logic/functors.cpp -c -fPIC -o functors.o && clang++ -dynamiclib -install_name libfunctors.dylib -o libfunctors.dylib functors.o
//
// linux
// g++ --std=c++20 -I $(dirname $(which souffle))/../include -I $(dirname $(which souffle))/../include/souffle src/ctadl/souffle-logic/functors.cpp -c -fPIC -o functors.o && g++ -shared -o libfunctors.so functors.o 
//
// ; export DYLD_LIBRARY_PATH=`pwd`
// clang-format on
#include <cstdint>
#include <cassert>
#include <string>
#include <algorithm>

#include "SouffleFunctor.h"

#define HI_FRAME_SEPARATOR_CHAR '#'

// frame is <name>#
// empty stack is ""
// 's' is var for call string

extern "C" {

static bool string_starts_with(const std::string& s1, const std::string& s2) {
  if (s2.length() > s1.length()) {
    return false;
  }
  return s1.compare(0, s2.length(), s2) == 0;
}

static bool string_ends_with(const std::string& s1, const std::string& s2) {
  if (s2.length() > s1.length()) {
    return false;
  }
  return s1.compare(s1.length() - s2.length(), s2.length(), s2) == 0;
}

souffle::RamDomain NewCallString(souffle::SymbolTable *symbolTable,
                                 souffle::RecordTable *recordTable) {
  assert(symbolTable && "NULL symbol table");
  assert(recordTable && "NULL record table");
  std::string stack;
  return symbolTable->encode(stack);
}

// bar1# ""
// mid#bar1# ""
// mid#bar1# bar1# 
// arg1 is more specific than arg2
// everything from context arg2 applies to arg1
int32_t CallStringLte(const char *arg1, const char *arg2) {
  std::string s1(arg1, strlen(arg1));
  std::string s2(arg2, strlen(arg2));
  return string_ends_with(s1, s2) ? 1 : 0;
}

// bar1# is "under" bar1#bar#
// If something holds in bar1#, it also holds in bar1#bar#
int32_t CallStringUnder(const char *arg1, const char *arg2) {
  std::string s1(arg1, strlen(arg1));
  std::string s2(arg2, strlen(arg2));
  return string_starts_with(s2, s1) ? 1 : 0;
}

int32_t CallStringNonEmpty(const char *arg1) {
  for (char *p = (char *) arg1; *p != '\0'; ++p) {
    if (*p == HI_FRAME_SEPARATOR_CHAR) {
      return 1;
    };
  }
  return 0;
}

int32_t CallStringSize(const char *arg1) {
  std::string s1(arg1, strlen(arg1));
  int32_t count = 0;
  for (auto it = s1.begin(), ie = s1.end(); it != ie; ++it) {
    if (*it == HI_FRAME_SEPARATOR_CHAR) {
      count++;
    }
  }
  return count;
}

// Reads the top frame of the call string
// Precondition: s contains '#'
souffle::RamDomain TopFrame(souffle::SymbolTable *symbolTable,
                            souffle::RecordTable *recordTable,
                            souffle::RamDomain arg1) {
  assert(symbolTable && "NULL symbol table");
  assert(recordTable && "NULL record table");
  const std::string &s = symbolTable->decode(arg1);
  std::string::size_type index = s.find_first_of(HI_FRAME_SEPARATOR_CHAR);
  if (index == std::string::npos) {
    return symbolTable->encode("");
  }
  assert(index != std::string::npos);
  std::string result(s, 0, index);
  return symbolTable->encode(result);
}

static souffle::RamDomain push_frame_helper(const std::string &function,
                                            const std::string &s,
                                            souffle::SymbolTable *symbolTable) {
  std::string result;
  result.reserve(function.size() + 1 + s.size());
  result.append(function).append(1, HI_FRAME_SEPARATOR_CHAR).append(s);
  return symbolTable->encode(result);
}

// Pushes a new function into the call string and returns it
// - arg1: function
// - arg2: call string
souffle::RamDomain PushFrame(souffle::SymbolTable *symbolTable,
                             souffle::RecordTable *recordTable,
                             souffle::RamDomain arg1, souffle::RamDomain arg2) {
  assert(symbolTable && "NULL symbol table");
  assert(recordTable && "NULL record table");
  const std::string &function = symbolTable->decode(arg1);
  const std::string &s = symbolTable->decode(arg2);
  return push_frame_helper(function, s, symbolTable);
}

// - arg1: function
// - arg2: call string
// - arg3: k
// Precondition: k > 0
souffle::RamDomain PushFrameK(souffle::SymbolTable *symbolTable,
                              souffle::RecordTable *recordTable,
                              souffle::RamDomain arg1, souffle::RamDomain arg2,
                              souffle::RamDomain k) {
  assert(symbolTable && "NULL symbol table");
  assert(recordTable && "NULL record table");
  assert(k > 0);
  const std::string &function = symbolTable->decode(arg1);
  const std::string &s = symbolTable->decode(arg2);
  std::string::size_type i = 0;
  // count of frames
  souffle::RamDomain count = 0;
  // 0 <= i < s.size()
  // s[0..i] contains 'count' occurrences of '#'
  for (i = 0; i < s.size() && count < (k-1); i++) {
    if (s[i] == HI_FRAME_SEPARATOR_CHAR) {
      count++;
    }
  }
  if (i < s.size()) {
    // everything from i should be deleted
    std::string s_restricted(s, 0, i);
    return push_frame_helper(function, s_restricted, symbolTable);
  }
  return push_frame_helper(function, s, symbolTable);
}

// Precondition: s contains "#"
// Returns new (possibly-empty) call string with top frame removed
souffle::RamDomain PopFrame(souffle::SymbolTable *symbolTable,
                            souffle::RecordTable *recordTable,
                            souffle::RamDomain arg1) {
  assert(symbolTable && "NULL symbol table");
  assert(recordTable && "NULL record table");
  const std::string &s = symbolTable->decode(arg1);
  std::string::size_type index = s.find_first_of(HI_FRAME_SEPARATOR_CHAR);
  if (index == std::string::npos) {
    return symbolTable->encode("");
  }
  assert(index != std::string::npos);
  index++; // skip #
  std::string result(s, index);
  return symbolTable->encode(result);
}

int32_t AccessPathSize(const char *arg1) {
  std::string s(arg1, strlen(arg1));
  int count = std::count_if(s.begin(), s.end(),
      [](char c) { return c == '.'; });
  return count;
}

int32_t AccessPathCycle(const char *arg1) {
  std::string s(arg1, strlen(arg1));
  // Finds each occurrence of ".". From there, finds a next occurrence of . or
  // the end of the string. The indices are (i, j).
  // We then search for an occurrence of substr starting *before* the index of
  // ".". And for the same substring *after* the index of ".". If either of
  // these hits, there is a cycle.
  // Otherwise, return 0.
  int32_t cyclic = 0;
  //std::cerr << "ap is '" << s << "' start" << std::endl;
  for (std::string::iterator it = s.begin(); it != s.end(); ++it) {
    if (!(*it == '.')) {
      continue;
    }
    if (it == s.end()) {
      goto done;
    }
    std::string::iterator it2;
    for (it2 = it+1; it2 != s.end(); ++it2) {
      if (*it2 == '.') {
        break;
      }
    }
    // it to it2 is the span of a substring. indices (i,j)
    int i = std::distance(s.begin(), it);
    int j = std::distance(s.begin(), it2);
    std::string field = s.substr(i, j-i);
    //std::cerr << "> field is '" << field << "' " << i << "," << j << std::endl;
    // Find first occurrence
    size_t pos = s.find(field, 0);
    if (pos != std::string::npos && pos != i) {
      cyclic = 1;
      goto done;
    }
    size_t pos2 = s.find(field, pos+1);
    if (pos2 != std::string::npos && pos2 != i) {
      cyclic = 1;
      goto done;
    }
  }
done:
  //std::cerr << "ap is '" << s << "' " << cyclic << std::endl;
  return cyclic;
}

// Given a classname like "a.b.Class", returns the Dex/JVM style class name
// "La/b/Class;".
souffle::RamDomain AndroidManifestClassId(
    souffle::SymbolTable *symbolTable,
    souffle::RecordTable *recordTable,
    souffle::RamDomain arg1) {
  assert(symbolTable && "NULL symbol table");
  assert(recordTable && "NULL record table");
  const std::string &s = symbolTable->decode(arg1);
  std::string jvm_name;
  jvm_name.append("L");
  jvm_name.append(s);
  jvm_name.append(";");
  size_t pos = 0;

  // Find the first occurrence of '.' and replace it with '/'
  while ((pos = jvm_name.find('.', pos)) != std::string::npos) {
    jvm_name.replace(pos, 1, "/");
    pos++; // Move past the last replaced character
  }
  return symbolTable->encode(jvm_name);
}

int CheckSubstring(const char *arg1, const char *arg2) {
  const std::string str1(arg1, strlen(arg1));
  const std::string str2(arg2, strlen(arg2));
  if (str1.find(str2) != std::string::npos) {
    return 1;
  } else if (str2.find(str1) != std::string::npos) {
    return 2;
  }
  return 0;
}

}
