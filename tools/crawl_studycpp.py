#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C++学习网 (studycpp.cn) 全站教程爬虫
抓取所有章节的教程内容，保存为 Markdown 格式
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://www.studycpp.cn"
OUTPUT_DIR = "studycpp_docs"

# 所有章节及其页面
CHAPTERS = {
    "chapter0": {
        "title": "序章",
        "pages": [
            ("introduction-to-site", "0.0 网站简介"),
            ("introduction-to-programming-languages", "0.1 什么是编程语言"),
            ("introduction-to-c-cpp", "0.2 C与C++"),
            ("introduction-to-development", "0.3 程序开发流程"),
            ("install-dev-env", "0.4 安装开发环境"),
            ("write-first-program", "0.5 第一个C++程序"),
        ]
    },
    "chapter1": {
        "title": "第一章 基础知识",
        "pages": [
            ("program-structure", "1.0 程序结构介绍"),
            ("comment", "1.1 注释"),
            ("variable", "1.2 对象与变量"),
            ("variable-init-assign", "1.3 变量初始化和赋值"),
            ("iostream", "1.4 iostream:cout、cin和endl简介"),
            ("uninit-variable", "1.5 未初始化的变量及未定义的行为"),
            ("keywords-and-naming-identifiers", "1.6 关键字和变量命名规则"),
            ("whitespace", "1.7 空白字符与代码样式"),
            ("literal-operator", "1.8 字面值和操作符简介"),
            ("exp", "1.9 表达式简介"),
            ("dev-first-program", "1.10 开发第一个程序"),
            ("summary", "1.11 第1章总结"),
        ]
    },
    "chapter2": {
        "title": "第二章 函数",
        "pages": [
            ("intro-func", "2.0 函数简介"),
            ("func-ret", "2.1 函数返回值"),
            ("func-ret-void", "2.2 无返回值函数"),
            ("func-arg", "2.3 函数参数简介"),
            ("local-var", "2.4 局部变量"),
            ("why-func", "2.5 为什么需要函数"),
            ("forward-declare", "2.6 前向声明"),
            ("multi-file", "2.7 多代码文件程序"),
            ("namespace", "2.8 命名冲突和名称空间简介"),
            ("preprocess", "2.9 预处理器简介"),
            ("header-file", "2.10 头文件"),
            ("header-guard", "2.11 头文件保护"),
            ("design-first-program", "2.12 设计第一个程序"),
            ("summary", "2.13 第2章总结"),
        ]
    },
    "chapter3": {
        "title": "第三章 程序调试",
        "pages": [
            ("syntax-semantic-errors", "3.0 语法和语义错误"),
            ("debug-process", "3.1 程序调试过程"),
            ("debug-strategy", "3.2 调试策略"),
            ("debug-tatics", "3.3 基本调试策略"),
            ("more-tatics", "3.4 更多调试策略"),
            ("step", "3.5 使用集成调试器：单步执行"),
            ("breakpoint", "3.6 断点"),
            ("watch-var", "3.7 监视变量"),
            ("call-stack", "3.8 调用堆栈"),
            ("avoid-problem", "3.9 在问题变成问题前进行避免"),
            ("summary", "3.10 第3章总结"),
        ]
    },
    "chapter4": {
        "title": "第四章 基本数据类型",
        "pages": [
            ("intro", "4.0 基本数据类型简介"),
            ("void", "4.1 Void"),
            ("size-of", "4.2 对象大小和sizeof运算符"),
            ("sign-int", "4.3 有符号整数"),
            ("unsign-int", "4.4 无符号整数，以及为什么要避免使用它们"),
            ("fix-int", "4.5 固定宽度整数和size_t"),
            ("sci-notation", "4.6 科学记数法"),
            ("float", "4.7 浮点数"),
            ("bool", "4.8 布尔值（Boolean）"),
            ("if", "4.9 if语句简介"),
            ("char", "4.10 字符"),
            ("type-convert", "4.11 类型转换和static_cast简介"),
            ("summary", "4.12 第4章总结"),
        ]
    },
    "chapter5": {
        "title": "第五章 常量，字符串",
        "pages": [
            ("const-var", "5.0 常量（命名常量）"),
            ("const-exp", "5.1 常量表达式、编译时常量和运行时常量"),
            ("constexpr", "5.2 Constexpr"),
            ("literal", "5.3 字面值常量"),
            ("num-sys", "5.4 数字系统（十进制、二进制、十六进制和八进制）"),
            ("cond-op", "5.5 条件运算符"),
            ("inline", "5.6 内联函数和变量"),
            ("const-eval", "5.7 Constexpr和consteval函数"),
            ("string", "5.8 std::string简介"),
            ("string-view", "5.9 std::string_view简介"),
            ("string-view2", "5.10 std::string_view（第2部分）"),
            ("summary", "5.11 第五章总结"),
        ]
    },
    "chapter6": {
        "title": "第六章 运算符",
        "pages": [
            ("op-precedence", "6.0 运算符优先级和结合性"),
            ("arithmetic-op", "6.1 算术运算符"),
            ("remaind-exp", "6.2 余数和指数"),
            ("incre-decre", "6.3 自增/自减运算符和副作用"),
            ("comma", "6.4 逗号运算符"),
            ("relation-op", "6.5 关系运算符和浮点比较"),
            ("logic-op", "6.6 逻辑运算符"),
            ("summary", "6.7 第六章总结"),
        ]
    },
    "chapter7": {
        "title": "第七章 作用域与编译链接",
        "pages": [
            ("code-block", "7.0 代码块"),
            ("user-def-namespace", "7.1 自定义命名空间和作用域解析操作符"),
            ("local-var", "7.2 局部变量"),
            ("global-var", "7.3 全局变量"),
            ("name-shadow", "7.4 变量名称遮挡（Variable shadowing）"),
            ("internal-link", "7.5 内部链接"),
            ("external-link", "7.6 外部链接和变量前向声明"),
            ("why-non-const-global-var-evil", "7.7 为什么（非常量）全局变量是邪恶的"),
            ("share-const-global", "7.8 在多个文件中共享全局常量（使用内联变量）"),
            ("static-local-var", "7.9 静态局部变量"),
            ("scope-duration-linkage", "7.10 作用域、存储期和链接摘要"),
            ("using", "7.11 using声明和using指令"),
            ("unname-namespace", "7.12 未命名与内联的命名空间"),
            ("summary", "7.13 第七章总结"),
        ]
    },
    "chapter8": {
        "title": "第八章 控制流与错误处理",
        "pages": [
            ("control-flow-intro", "8.0 控制流简介"),
            ("if-block", "8.1 If语句与代码块"),
            ("if-problem", "8.2 常见的if语句问题"),
            ("constexpr-if", "8.3 Constexpr if语句"),
            ("switch", "8.4 Switch语句基础"),
            ("switch-fallthrough-scope", "8.5 switch fallthrough机制与作用域"),
            ("goto", "8.6 goto语句"),
            ("loop", "8.7 循环和while语句简介"),
            ("do-while", "8.8 Do while语句"),
            ("for", "8.9 for语句"),
            ("break-continue", "8.10 break与continue"),
            ("halt", "8.11 提前退出程序"),
            ("random-intro", "8.12 随机数生成简介"),
            ("random-ms", "8.13 使用Mersenne Twister生成随机数"),
            ("random-global", "8.14 全局随机数"),
            ("summary", "8.15 第八章总结"),
        ]
    },
    "chapter9": {
        "title": "第九章 错误检查与处理",
        "pages": [
            ("intro", "9.0 代码测试简介"),
            ("code-coverage", "9.1 代码覆盖率"),
            ("common-semantic-errors", "9.2 常见的语义错误"),
            ("detect-handle-error", "9.3 检测和处理错误"),
            ("cin-error-handle", "9.4 std::cin和处理无效输入"),
            ("assert", "9.5 断言"),
            ("summary", "9.6 第9章总结"),
        ]
    },
    "chapter10": {
        "title": "第十章 类型转换，类型别名与类型推导",
        "pages": [
            ("implicit-type-convert", "10.0 隐式类型转换"),
            ("promotion", "10.1 数值提升"),
            ("num-convert", "10.2 数值转换"),
            ("narrow-convert-list-constexpr-init", "10.3 窄化转换、列表初始化和constexpr初始化"),
            ("arithmetic-convert", "10.4 算术转换"),
            ("explicit-type-convert-static-cast", "10.5 显式类型转换和static_cast"),
            ("typedef", "10.6 typedef和类型别名"),
            ("auto-type-object", "10.7 使用auto关键字的对象类型自动推导"),
            ("auto-type-func", "10.8 函数的类型推导"),
            ("summary", "10.9 第10章总结"),
        ]
    },
    "chapter11": {
        "title": "第十一章 函数重载与函数模版",
        "pages": [
            ("func-overload-intro", "11.0 函数重载简介"),
            ("func-overload-diff", "11.1 被重载函数之间互相区分"),
            ("func-overload-resolution", "11.2 函数重载决议"),
            ("func-del", "11.3 函数的delete说明符"),
            ("default-param", "11.4 默认参数"),
            ("func-template", "11.5 函数模板"),
            ("func-template-instane", "11.6 函数模板实例化"),
            ("func-template-mutli-type", "11.7 具有多个模板类型的函数模板"),
            ("func-template-none-type-param", "11.8 非类型模板参数"),
            ("summary", "11.9 第11章总结"),
        ]
    },
    "chapter12": {
        "title": "第十二章 复合类型：引用与指针",
        "pages": [
            ("compound-data-intro", "12.0 复合数据类型简介"),
            ("value-category", "12.1 值类别（左值 lvalue 和右值 rvalue）"),
            ("lvalue-ref", "12.2 左值引用"),
            ("const-lvalue-ref", "12.3 const的左值引用"),
            ("lvalue-ref-func-arg", "12.4 通过左值引用传递函数参数"),
            ("const-lvalue-ref-func-arg", "12.5 通过常量左值引用传递函数参数"),
            ("pointer-intro", "12.6 指针简介"),
            ("null-ptr", "12.7 空指针"),
            ("const-ptr", "12.8 指针与常量"),
            ("pointer-func-arg", "12.9 通过指针传递函数参数"),
            ("pointer-func-arg-two", "12.10 通过指针传递函数参数（第2部分）"),
            ("ret-ref-pointer", "12.11 引用或指针作为函数返回值"),
            ("io-args", "12.12 输入和输出参数"),
            ("auto-type-deduct-ptr-ref-const", "12.13 指针、引用和常量的类型自动推导"),
            ("summary", "12.14 第12章总结"),
        ]
    },
    "chapter13": {
        "title": "第十三章 复合类型：枚举与结构体",
        "pages": [
            ("user_define_type", "13.0 用户自定义类型简介"),
            ("unscoped-enum", "13.1 非限定作用域枚举"),
            ("unscoped-enum-io", "13.2 非限定作用域枚举的输入与输出"),
            ("scoped-enum", "13.3 限定作用域枚举（枚举类）"),
            ("struct-intro", "13.4 结构体简介"),
            ("struct-init", "13.5 结构体初始化"),
            ("struct-member-default-init", "13.6 成员变量的默认初始化"),
            ("struct-arg-ret", "13.7 结构体作为函数的输入与输出"),
            ("struct-other", "13.8 结构体杂项"),
            ("struct-member-select", "13.9 结构体指针和引用的成员选择操作"),
            ("class-template", "13.10 类模板"),
            ("class-template-arg-deduct", "13.11 类模板参数推导（CTAD）"),
            ("template-alias", "13.12 模板别名"),
            ("summary", "13.13 第13章总结"),
            ("use-cpp-ref", "13.14 如何使用c++语言手册"),
        ]
    },
    "chapter14": {
        "title": "第十四章 class介绍",
        "pages": [
            ("intro-oop", "14.0 面向对象编程简介"),
            ("intro-class", "14.1 class简介"),
            ("member_func", "14.2 成员函数"),
            ("const-obj", "14.3 Const类对象和Const成员函数"),
            ("public-private", "14.4 公共和私有成员以及访问说明符"),
            ("access-func", "14.5 访问函数"),
            ("member-func-ret-member-data-ref", "14.6 成员函数返回对数据成员的引用"),
            ("data-hide", "14.7 数据隐藏（封装）的好处"),
            ("construct", "14.8 构造函数简介"),
            ("construct-member-init-list", "14.9 构造函数成员初始化列表"),
            ("default_construct", "14.10 默认构造函数和默认参数"),
            ("delegate_construct", "14.11 委托构造函数"),
            ("tmp_obj", "14.12 临时类对象"),
            ("copy-construct", "14.13 拷贝构造函数简介"),
            ("class-init-copy-elision", "14.14 类初始化和拷贝省略"),
            ("convert-construct-explict", "14.15 转换构造函数和explicit关键字"),
            ("summary", "14.16 第14章总结"),
        ]
    },
    "chapter15": {
        "title": "第十五章 class第二部分",
        "pages": [
            ("hide-this", "15.0 隐藏的this指针和成员函数调用"),
            ("class-header-file", "15.1 类和头文件"),
            ("nest-type", "15.2 嵌套类型（成员类型）"),
            ("destruct-intro", "15.3 析构函数简介"),
            ("class-tmplate-with-member-func", "15.4 具有成员函数的类模板"),
            ("static-member-var", "15.5 静态成员变量"),
            ("static-member-func", "15.6 静态成员函数"),
            ("friend-no-member-func", "15.7 友元非成员函数"),
            ("friend-class", "15.8 友元类和友元成员函数"),
            ("ref-qulify", "15.9 引用限定符"),
            ("summary", "15.10 第15章总结"),
        ]
    },
    "chapter16": {
        "title": "第十六章 动态数组：std::vector",
        "pages": [
            ("intro-container-array", "16.0 容器和数组简介"),
            ("intro-vector-list-init", "16.1 std::vector和列表构造函数简介"),
            ("vec-len", "16.2 vector与无符号长度和下标问题"),
            ("vec-pass", "16.3 传递std::vector"),
            ("vec-ret-move", "16.4 返回std::vector，移动语义简介"),
            ("vec-loop", "16.5 数组和循环"),
            ("vec-loop-sign-index", "16.6 数组、循环和有符号下标"),
            ("range-for", "16.7 基于范围的for循环（range for / for each）"),
            ("enum-as-index", "16.8 使用枚举值来作为数组索引"),
            ("vec-size-capacity", "16.9 std::vector大小调整和容量"),
            ("vec-stack", "16.10 std::vector和栈行为"),
            ("vec-bool", "16.11 std::vector<bool>"),
            ("summary", "16.12 第16章总结"),
        ]
    },
    "chapter17": {
        "title": "第十七章 固定长度数组：std::array与c样式数组",
        "pages": [
            ("arr-intro", "17.0 std::array简介"),
            ("arr-len-index", "17.1 std::array长度和索引"),
            ("arr-pass-ret", "17.2 std::array作为函数参数或返回值"),
            ("arr-of-class", "17.3 std::array与类类型元素"),
            ("arr-ref", "17.4 通过std::reference_wrapper创建引用的数组"),
            ("arr-enum", "17.5 std::array和枚举"),
            ("c-arr", "17.6 C样式数组简介"),
            ("c-arr-decay", "17.7 C样式数组退化"),
            ("pointer-arithmetic", "17.8 指针运算和下标"),
            ("c-str", "17.9 C样式字符串"),
            ("c-const-str", "17.10 常量C样式字符串"),
            ("c-multi-arr", "17.11 多维C样式数组"),
            ("std-multi-arr", "17.12 多维std::array"),
            ("summary", "17.13 第17章总结"),
        ]
    },
    "chapter18": {
        "title": "第十八章 迭代器与算法",
        "pages": [
            ("sort-arr", "18.0 对数组进行排序"),
            ("iter", "18.1 迭代器简介"),
            ("std-algorithm", "18.2 算法标准库简介"),
            ("time-code", "18.3 为代码计时"),
        ]
    },
    "chapter19": {
        "title": "第十九章 动态内存分配",
        "pages": [
            ("new-delete", "19.0 使用new和delete进行动态分配内存"),
            ("new-delete-arr", "19.1 动态分配数组"),
            ("destructor", "19.2 再谈析构函数"),
            ("ptr-to-ptr", "19.3 指向指针和动态多维数组的指针"),
            ("void-ptr", "19.4 void指针"),
        ]
    },
    "chapter20": {
        "title": "第二十章 函数",
        "pages": [
            ("func-ptr", "20.0 函数指针"),
            ("heap-stack", "20.1 堆和栈"),
            ("recursion", "20.2 递归"),
            ("cmd-args", "20.3 命令行参数"),
            ("ellipsis", "20.4 省略号与可变参数（以及为什么要避免它们）"),
            ("lambda", "20.5 lambda（匿名函数）简介"),
            ("lambda-capture", "20.6 Lambda捕获"),
            ("summary", "20.7 第20章总结"),
        ]
    },
    "chapter21": {
        "title": "第二十一章 操作符重载",
        "pages": [
            ("op-overload-intro", "21.0 操作符重载简介"),
            ("friend-op-overload", "21.1 使用友元函数重载算术运算符"),
            ("normal-op-overload", "21.2 使用普通函数重载运算符"),
            ("overload-io", "21.3 重载I/O运算符"),
            ("member-op-overload", "21.4 使用成员函数重载运算符"),
            ("unary-op-overload", "21.5 重载一元运算符+、-和！"),
            ("compare-op-overload", "21.6 重载比较运算符"),
            ("incr-decre-overload", "21.7 重载递增和递减运算符"),
            ("subscript-overload", "21.8 重载下标运算符"),
            ("parenthesis-overload", "21.9 重载括号运算符"),
            ("type-cast-overload", "21.10 重载类型转换"),
            ("assign-op-overload", "21.11 重载赋值运算符"),
            ("shadow-deep-copy", "21.12 浅拷贝与深拷贝"),
            ("op-overload-template", "21.13 重载运算符和函数模板"),
            ("summary", "21.14 第21章总结"),
        ]
    },
    "chapter22": {
        "title": "第二十二章 移动语义与智能指针",
        "pages": [
            ("move-smart-pointer-intro", "22.0 智能指针和移动语义简介"),
            ("r-value-ref", "22.1 右值引用"),
            ("move-construct-assign", "22.2 移动构造函数和移动赋值函数"),
            ("std-move", "22.3 std::move"),
            ("unique-ptr", "22.4 std::unique_ptr"),
            ("shared-ptr", "22.5 std::shared_ptr"),
            ("circle-ref", "22.6 std::shared_ptr的循环依赖性问题和std::weak_ptr"),
            ("summary", "22.7 第22章总结"),
        ]
    },
    "chapter23": {
        "title": "第二十三章 对象关系",
        "pages": [
            ("object-relation", "23.0 对象关系"),
            ("composition", "23.1 对象组合"),
            ("aggregation", "23.2 聚合"),
            ("association", "23.3 关联"),
            ("dependencies", "23.4 依赖关系"),
            ("container-class", "23.5 容器类"),
            ("initializer-list", "23.6 std::initializer_list"),
            ("summary", "23.7 第23章总结"),
        ]
    },
    "chapter24": {
        "title": "第二十四章 继承",
        "pages": [
            ("inherit-intro", "24.0 继承简介"),
            ("inherit-basic", "24.1 基本继承"),
            ("derived-class-cons-order", "24.2 派生类的构造顺序"),
            ("derived-class-cons-init", "24.3 派生类的构造函数与初始化"),
            ("inherit-access-spec", "24.4 继承和访问说明符"),
            ("add-new-func-to-derived-class", "24.5 向派生类添加新功能"),
            ("call-inherit-func-and-overload", "24.6 调用继承的函数与重写行为"),
            ("hide-inherit-func", "24.7 隐藏继承的功能"),
            ("multiple-inherit", "24.8 多重继承"),
            ("summary", "24.9 第24章总结"),
        ]
    },
    "chapter25": {
        "title": "第二十五章 虚函数",
        "pages": [
            ("base-pointer-ref-to-derived", "25.0 指向派生对象的基类指针和引用"),
            ("virtual-func", "25.1 虚函数和多态"),
            ("override-final", "25.2 override和final说明符"),
            ("virtual-destructor-assign-override", "25.3 虚析构函数、虚赋值函数以及虚函数重写"),
            ("early-bind-late-bind", "25.4 静态绑定和动态绑定"),
            ("virtual-table", "25.5 虚函数表"),
            ("abstract-class", "25.6 纯虚函数、抽象基类和接口类"),
            ("virtual-base-class", "25.7 虚基类"),
            ("object-slice", "25.8 对象切片（Object slicing）"),
            ("dynamic-cast", "25.9 dynamic_cast"),
            ("print-inherit-class", "25.10 使用运算符<<打印继承的类"),
            ("summary", "25.11 第25章总结"),
        ]
    },
    "chapter26": {
        "title": "第二十六章 模板",
        "pages": [
            ("template-class", "26.0 模板类"),
            ("no-type-template-param", "26.1 模板非类型参数"),
            ("func-template-specialization", "26.2 函数模板特化"),
            ("class-template-specialization", "26.3 类模板特化"),
            ("part-template-special", "26.4 部分模板特化"),
            ("pointer-part-template-special", "26.5 指针的部分模板特化"),
            ("summary", "26.6 第26章总结"),
        ]
    },
    "chapter27": {
        "title": "第二十七章 异常",
        "pages": [
            ("exception-need", "27.0 为什么需要异常机制"),
            ("exception-basic", "27.1 基本异常处理"),
            ("exception-func-stack-unwind", "27.2 异常、函数和堆栈展开"),
            ("uncatch-catchall", "27.3 未捕获的异常和捕获所有异常"),
            ("exception-and-class", "27.4 异常、类和继承"),
            ("exception-rethrow", "27.5 重新抛出异常"),
            ("function-try", "27.6 函数try块"),
            ("exception-downside", "27.7 异常的风险和缺点"),
            ("exception-spec-noexcept", "27.8 异常规格和noexcept"),
            ("move-if-noexcept", "27.9 std::move_if_noexcept"),
            ("summary", "27.10 第27章总结"),
        ]
    },
    "chapter28": {
        "title": "第二十八章 输入输出（I/O）",
        "pages": [
            ("io-stream", "28.0 输入和输出（I/O）流"),
            ("istream", "28.1 使用istream处理输入"),
            ("ostream", "28.2 使用ostream和ios输出"),
            ("stream-for-string", "28.3 针对字符串的stream类"),
            ("stream-state-validate-input", "28.4 流的状态和输入验证"),
            ("basic-file-io", "28.5 基本文件I/O"),
            ("random-file-io", "28.6 随机文件I/O"),
        ]
    },
}


def sanitize_filename(name):
    """清理文件名中的非法字符"""
    return re.sub(r'[<>:"/\\|?*]', '-', name)


def fetch_page(url, timeout=30):
    """获取页面内容"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.encoding = 'utf-8'
        if resp.status_code == 200:
            return resp.text
        else:
            print(f"  [错误] HTTP {resp.status_code}: {url}")
            return None
    except Exception as e:
        print(f"  [错误] 请求失败: {e}")
        return None


def extract_content(html, page_title):
    """从 HTML 中提取教程正文内容，转换为 Markdown

    页面结构: #main-container > .row > .col-md-8.card (正文)
    策略: 遍历 .card 的直接子元素，跳过已知的非正文元素
    """
    soup = BeautifulSoup(html, 'html.parser')

    # 定位正文区域
    content_area = soup.select_one('.col-md-8.card')
    if not content_area:
        content_area = soup.select_one('.card')
    if not content_area:
        return f"# {page_title}\n\n> 无法解析页面内容"

    # 提取 h1 标题
    h1_tag = content_area.find('h1')
    if h1_tag:
        title_text = h1_tag.get_text(strip=True)
    else:
        title_text = page_title

    md_lines = [f"# {title_text}", "", f"> 来源: C++学习网 (studycpp.cn)", ""]

    # 遍历 .card 的直接子元素
    reached_footer = False  # 标记是否到达页脚区域（导航/评论区之后）
    for elem in content_area.find_all(recursive=False):
        if reached_footer:
            break

        tag = elem.name
        classes = elem.get('class', [])
        elem_id = elem.get('id', '')

        # 跳过非正文元素
        if tag in ('script', 'style', 'nav', 'footer', 'img', 'button', 'input'):
            continue
        if tag == 'span' and 'waline' in ' '.join(classes).lower():
            continue
        if elem_id == 'waline':
            reached_footer = True  # 评论区之后的都跳过
            continue
        if tag == 'h1':
            continue  # 已在上面处理

        # 跳过导航行 (上一页/下一页)
        if tag == 'div' and 'row' in classes:
            nav_text = elem.get_text(strip=True)
            if any(w in nav_text for w in ['上一节', '下一节', '主页']):
                reached_footer = True  # 导航之后的 hr 也跳过
                continue

        cls_str = ' '.join(classes).lower()

        if tag == 'hr':
            md_lines.extend(["", "---", ""])

        elif tag.startswith('h') and len(tag) == 2 and tag[1].isdigit():
            level = int(tag[1])
            text = elem.get_text(strip=True)
            if text:
                md_lines.extend(["", f"{'#' * level} {text}", ""])

        elif tag == 'p':
            text = process_inline_elements(elem)
            if text.strip():
                md_lines.extend(["", text, ""])

        elif tag == 'pre':
            code_tag = elem.find('code')
            if code_tag:
                lang = ""
                code_classes = code_tag.get('class', [])
                if code_classes:
                    for c in code_classes:
                        if c.startswith('language-'):
                            lang = c.replace('language-', '')
                            break
                code_text = code_tag.get_text()
                md_lines.extend(["", f"```{lang}", code_text.strip(), "```", ""])
            else:
                code_text = elem.get_text()
                if code_text.strip():
                    md_lines.extend(["", "```", code_text.strip(), "```", ""])

        elif tag in ('ul', 'ol'):
            md_lines.append("")
            for li in elem.find_all('li', recursive=False):
                prefix = "- " if tag == 'ul' else "1. "
                li_text = process_inline_elements(li)
                md_lines.append(f"{prefix}{li_text}")
            md_lines.append("")

        elif tag == 'table':
            md_lines.extend(process_table(elem))

        elif tag == 'blockquote':
            text = elem.get_text(strip=True)
            if text:
                md_lines.extend(["", f"> {text}", ""])

        elif tag == 'div':
            # 先递归提取其中的代码块
            _extract_code_blocks(elem, md_lines)
            # alert 提示框
            if 'alert' in cls_str:
                text = elem.get_text(strip=True)
                if text:
                    md_lines.extend(["", f"> **提示:** {text}", ""])
            else:
                # 递归处理 div 中的子元素
                _process_div_children(elem, md_lines)

        elif tag == 'table':
            _extract_code_blocks(elem, md_lines)
            md_lines.extend(process_table(elem))

        elif tag == 'span':
            # 跳过 waline 统计等
            pass

    result = "\n".join(md_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


def _extract_code_blocks(elem, md_lines):
    """递归提取元素中的代码块（处理嵌套 table/div 中的 pre）"""
    for pre in elem.find_all('pre'):
        # 跳过已经是 ul/ol 项中的（已经处理过）
        parent = pre.parent
        if parent and parent.name == 'li':
            continue
        # 寻找 code 标签
        code_tag = pre.find('code')
        if not code_tag:
            continue
        # 跳过行号代码块（只有数字的）
        code_text = code_tag.get_text().strip()
        if not code_text:
            continue
        # 检查是否是纯行号块
        lines = code_text.split('\n')
        if all(line.strip().isdigit() or line.strip() == '' for line in lines):
            continue
        
        lang = ""
        classes = code_tag.get('class', [])
        if classes:
            for c in classes:
                if c.startswith('language-'):
                    lang = c.replace('language-', '')
                    break
        md_lines.extend(["", f"```{lang}", code_text, "```", ""])


def _process_div_children(div_elem, md_lines):
    """递归处理 div 中的子元素"""
    for child in div_elem.find_all(recursive=False):
        tag = child.name
        if tag in ('script', 'style'):
            continue
        if tag.startswith('h') and len(tag) == 2 and tag[1].isdigit():
            level = int(tag[1])
            text = child.get_text(strip=True)
            if text:
                md_lines.extend(["", f"{'#' * level} {text}", ""])
        elif tag == 'p':
            text = process_inline_elements(child)
            if text.strip():
                md_lines.extend(["", text, ""])
        elif tag == 'pre':
            _extract_code_blocks(child, md_lines)
        elif tag in ('ul', 'ol'):
            md_lines.append("")
            for li in child.find_all('li', recursive=False):
                prefix = "- " if tag == 'ul' else "1. "
                li_text = process_inline_elements(li)
                md_lines.append(f"{prefix}{li_text}")
            md_lines.append("")
        elif tag == 'table':
            # 表可能包含代码块，先检查
            _extract_code_blocks(child, md_lines)
            # 也转换为 markdown 表格
            table_md = process_table(child)
            md_lines.extend(table_md)
        elif tag == 'blockquote':
            text = child.get_text(strip=True)
            if text:
                md_lines.extend(["", f"> {text}", ""])
        elif tag == 'div':
            _extract_code_blocks(child, md_lines)
            _process_div_children(child, md_lines)


def process_inline_elements(elem):
    """处理行内元素，转换为 Markdown 格式"""
    result_parts = []
    for child in elem.children:
        if isinstance(child, str):
            result_parts.append(child)
        elif child.name == 'code':
            result_parts.append(f"`{child.get_text()}`")
        elif child.name in ('strong', 'b'):
            result_parts.append(f"**{child.get_text()}**")
        elif child.name in ('em', 'i'):
            result_parts.append(f"*{child.get_text()}*")
        elif child.name == 'a':
            href = child.get('href', '')
            text = child.get_text(strip=True)
            if href and not href.startswith('#'):
                full_url = urljoin(BASE_URL, href) if href.startswith('/') else href
                result_parts.append(f"[{text}]({full_url})")
            else:
                result_parts.append(text)
        elif child.name == 'img':
            alt = child.get('alt', '')
            src = child.get('src', '')
            if src:
                full_src = urljoin(BASE_URL, src) if src.startswith('/') else src
                result_parts.append(f"![{alt}]({full_src})")
        elif child.name == 'br':
            result_parts.append('\n')
        elif child.name in ('del', 's', 'strike'):
            result_parts.append(f"~~{child.get_text()}~~")
        elif child.name == 'mark':
            result_parts.append(f"=={child.get_text()}==")
        else:
            text = child.get_text() if hasattr(child, 'get_text') else str(child)
            if text:
                result_parts.append(text)
    return ''.join(result_parts)


def process_table(table_elem):
    """将 HTML 表格转换为 Markdown 表格"""
    lines = []
    rows = table_elem.find_all('tr')
    if not rows:
        return lines

    lines.append("")
    # 表头
    header_cols = []
    ths = rows[0].find_all(['th', 'td'])
    for th in ths:
        header_cols.append(th.get_text(strip=True))

    if header_cols:
        lines.append("| " + " | ".join(header_cols) + " |")
        lines.append("| " + " | ".join(["---"] * len(header_cols)) + " |")

    # 数据行
    for row in rows[1:]:
        cols = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
        if cols:
            lines.append("| " + " | ".join(cols) + " |")

    lines.append("")
    return lines


def crawl_all():
    """爬取所有页面"""
    total_pages = sum(len(ch["pages"]) for ch in CHAPTERS.values())
    print(f"C++学习网 全站爬虫")
    print(f"{'=' * 60}")
    print(f"总计: {len(CHAPTERS)} 个章节, {total_pages} 个页面")
    print(f"输出目录: {os.path.abspath(OUTPUT_DIR)}")
    print(f"{'=' * 60}")
    print()

    page_count = 0
    success_count = 0
    fail_count = 0

    for ch_key, ch_info in CHAPTERS.items():
        ch_title = ch_info["title"]
        ch_dir = os.path.join(OUTPUT_DIR, ch_key)
        os.makedirs(ch_dir, exist_ok=True)

        print(f"\n{'=' * 60}")
        print(f"  {ch_title} ({ch_key})")
        print(f"{'=' * 60}")

        for slug, page_title in ch_info["pages"]:
            page_count += 1
            url = f"{BASE_URL}/basic/{ch_key}/{slug}/"
            print(f"[{page_count}/{total_pages}] {page_title}")

            html = fetch_page(url)
            if html:
                markdown = extract_content(html, page_title)

                filename = sanitize_filename(f"{page_title}.md")
                filepath = os.path.join(ch_dir, filename)

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(markdown)

                success_count += 1
                print(f"  OK ({len(markdown)} chars)")
            else:
                fail_count += 1
                print(f"  FAILED")

            # 礼貌延迟
            time.sleep(0.5)

    # 生成总目录
    generate_index()

    print(f"\n{'=' * 60}")
    print(f"  抓取完成!")
    print(f"  总计: {total_pages} 页 | 成功: {success_count} | 失败: {fail_count}")
    print(f"  输出: {os.path.abspath(OUTPUT_DIR)}")
    print(f"{'=' * 60}")


def generate_index():
    """生成总目录 README.md"""
    lines = [
        "# C++学习网 教程全集",
        "",
        "> 来源: [https://www.studycpp.cn](https://www.studycpp.cn)",
        "> 本教程内容来源于 learncpp.com，中文翻译版本。",
        "",
        "## 目录",
        "",
    ]

    for ch_key, ch_info in CHAPTERS.items():
        lines.append(f"### {ch_info['title']}")
        lines.append("")
        for slug, page_title in ch_info["pages"]:
            filename = sanitize_filename(f"{page_title}.md")
            lines.append(f"- [{page_title}]({ch_key}/{filename})")
        lines.append("")

    lines.append("---")
    lines.append(f"*共 {len(CHAPTERS)} 个章节*")

    index_path = os.path.join(OUTPUT_DIR, "README.md")
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    print(f"\n  README 已生成: {os.path.abspath(index_path)}")


if __name__ == "__main__":
    crawl_all()
