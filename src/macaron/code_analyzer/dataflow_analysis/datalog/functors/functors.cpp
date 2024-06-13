/* Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved. */

#include <souffle/SouffleFunctor.h>
#include <filesystem>
#include <cstdint>
#include <string>

extern "C" { 
 souffle::RamDomain basename(souffle::SymbolTable* symbolTable, souffle::RecordTable* recordTable,
        souffle::RamDomain arg) {
    const std::string& sarg = symbolTable->decode(arg);
    std::filesystem::path p(sarg);
    std::string result = p.filename();
    return symbolTable->encode(result);
 }

 int32_t isUnderDir(const char *dirpath, const char *filepath) {
    std::string dirpathstr(dirpath);
    std::string filepathstr(filepath);
    if (dirpathstr.size() == 0) {
        return 0;
    }
    if (dirpath == filepath) {
        return 0;
    }
    if (dirpathstr[dirpathstr.size()-1] == '/') {
        if (filepathstr.substr(0, dirpathstr.size()) == dirpathstr) {
            return 1;
        }
    } else {
        if (filepathstr.substr(0, dirpathstr.size()+1) == (dirpathstr + "/")) {
            return 1;
        }
    }
    return 0;
 }
}