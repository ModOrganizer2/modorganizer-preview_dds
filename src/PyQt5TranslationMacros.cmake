# This is a modified version of Qt5LinguistToolsMacros.cmake which calls
# pylupdate5 instead of lupdate, allowing Python strings to be extracted,
# too. It still requires the Qt version of the file to be included, but
# only this version of the function needs to be called. You also need to
# have PYTHON_ROOT set to a directory where a working pylupdate5.bat can
# be found. If you aren't using Windows, your platform's equivalent may
# work, too.

#=============================================================================
# Copyright 2005-2011 Kitware, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# * Redistributions of source code must retain the above copyright
#   notice, this list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in the
#   documentation and/or other materials provided with the distribution.
#
# * Neither the name of Kitware, Inc. nor the names of its
#   contributors may be used to endorse or promote products derived
#   from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#=============================================================================

include(CMakeParseArguments)

function(PYQT5_CREATE_TRANSLATION _qm_files)
    set(options)
    set(oneValueArgs)
    set(multiValueArgs OPTIONS)

    cmake_parse_arguments(_LUPDATE "${options}" "${oneValueArgs}" "${multiValueArgs}" ${ARGN})
    set(_lupdate_files ${_LUPDATE_UNPARSED_ARGUMENTS})
    set(_lupdate_options ${_LUPDATE_OPTIONS})

    set(_my_sources)
    set(_my_tsfiles)
    foreach(_file ${_lupdate_files})
        get_filename_component(_ext ${_file} EXT)
        get_filename_component(_abs_FILE ${_file} ABSOLUTE)
        if(_ext MATCHES "ts")
            list(APPEND _my_tsfiles ${_abs_FILE})
        else()
            list(APPEND _my_sources ${_abs_FILE})
        endif()
    endforeach()
    foreach(_ts_file ${_my_tsfiles})
        set(_lst_file_srcs)
        if(_my_sources)
          # Qt made a file listing all sources and used that as an argument, but pylupdate5 doesn't support that.
          # Qt allowed directories to be listed as sources, but pylupdate5 requires their contents to be listed.
          get_filename_component(_ts_name ${_ts_file} NAME_WE)
          foreach(_lst_file_src ${_my_sources})
              if(IS_DIRECTORY ${_lst_file_src})
                file(GLOB _directory_contents ${_lst_file_src}/*.py ${_lst_file_src}/*.ui)
                list(APPEND _lst_file_srcs ${_directory_contents})
              else()
                list(APPEND _lst_file_srcs ${_lst_file_src})
              endif()
          endforeach()
        endif()
        add_custom_command(OUTPUT ${_ts_file}
            COMMAND ${PYTHON_ROOT}/PCbuild/amd64/python.exe
            ARGS -m PyQt5.pylupdate_main ${_lupdate_options} ${_lst_file_srcs} -ts ${_ts_file}
            DEPENDS ${_lst_file_srcs}
            WORKING_DIRECTORY ${PYTHON_ROOT}
            VERBATIM)
    endforeach()
    qt5_add_translation(${_qm_files} ${_my_tsfiles})
    set(${_qm_files} ${${_qm_files}} PARENT_SCOPE)
endfunction()
