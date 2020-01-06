# Version chosen arbitrarily
CMAKE_MINIMUM_REQUIRED(VERSION 3.0)

FIND_PACKAGE(Qt5LinguistTools)
INCLUDE(PyQt5TranslationMacros.cmake)
PYQT5_CREATE_TRANSLATION(preview_dds_translations_qm ${CMAKE_SOURCE_DIR}/src ${CMAKE_SOURCE_DIR}/src/DDS ${CMAKE_SOURCE_DIR}/src/DDSPreview_en.ts)

add_custom_target(translations ALL DEPENDS ${preview_dds_translations_qm})

add_subdirectory(DDS)

###############
## Installation

INSTALL(FILES
        ${CMAKE_CURRENT_SOURCE_DIR}/DDSPreview.py
        DESTINATION bin/plugins)