
一个有用的issue[https://github.com/joernio/joern/issues/585]
# 目前发现的问题（在joernv1.1.744上测试)
## 1.wchar_t* 的识别有问题(v1.1.751已解决）

源文件：CWE121_Stack_Based_Buffer_Overflow__CWE805_wchar_t_alloca_memmove_10.c
```
void CWE121_Stack_Based_Buffer_Overflow__CWE805_wchar_t_alloca_memmove_10_bad()
{
    wchar_t * data;
    wchar_t * dataBadBuffer = (wchar_t *)ALLOCA(50*sizeof(wchar_t));
    wchar_t * dataGoodBuffer = (wchar_t *)ALLOCA(100*sizeof(wchar_t));
    ……
```
Joern识别后的cpg中data的local代码部分却为wchar_t
```
joern> cpg.method("CWE121_Stack_Based_Buffer_Overflow__CWE805_wchar_t_alloca_memmove_10_bad").local.code.l 
res9: List[String] = List(
  "wchar_t data",
  "wchar_t dataBadBuffer",
  "wchar_t dataGoodBuffer",
  "wchar_t[100] source"
)
```
这就导致在提取指针关注点时无法提取到这些关注点

## 2.对c++引用传参的识别存在问题（v1.1.751参数类型已修改，但是调用关系还是存在问题）

源文件：CWE190_Integer_Overflow__int_fgets_square_43.cpp
```
static void badSource(int &data)
……

void bad()
{
   ……
    badSource(data);
   ……
}
```
badSource中的参数data使用了引用传参，但是在cpg中其类型为int *
```
joern> cpg.method("badSource").parameter.l 
res12: List[MethodParameterIn] = List(
  MethodParameterIn(
    id -> 9L,
    code -> "int &data",
    columnNumber -> Some(value = 23),
    dynamicTypeHintFullName -> ArraySeq(),
    evaluationStrategy -> "BY_VALUE",
    index -> 1,
    isVariadic -> false,
    lineNumber -> Some(value = 29),
    name -> "data",
    order -> 1,
    typeFullName -> "int*"
  )
 ```
这会导致两个问题：
- 在提取关注点时会将data作为指针类型的关注点。事实上，就算是真正的指针，其typeFullName中也不会有*，因此在提取指针关注点时可以仅考虑其code中是否包含*，而不用关注typeFullName属性。
- 在识别调用关系时出错，使用callIn方法查找调用该函数的位置，结果为空

但是事实上，在bad函数中调用了该函数，应该是在分析时由于参数类型不是int* ，因而joern认为调用的不是定义的badSource函数。

## 3.全局变量如何处理
切片是以函数为单位的，如何将全局变量加入是个问题，开会讨论结果是暂不处理
## 4.函数指针识别不了
## 5.类的成员函数识别不了调用关系




