#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/7/23 20:19
# @Author  : pikadoramon
# @File    : inject_exception.py
# @Software: PyCharm


class EmptyResponseError(ValueError):
    pass

class EmptyFieldError(ValueError):
    pass
