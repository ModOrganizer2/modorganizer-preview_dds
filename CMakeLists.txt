cmake_minimum_required(VERSION 3.16)

project(preview_dds LANGUAGES NONE)
set(project_type python_plugin)
set(enable_warnings OFF)

include(../cmake_common/project.cmake)
add_subdirectory(src)
