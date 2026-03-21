cmake_minimum_required(VERSION 3.20)

project(sharp_pc_e500_card_spade_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(e500_ft_host STATIC
  src/e500_ft_host.cpp
)

target_include_directories(e500_ft_host PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/src
)

if(APPLE)
  target_link_libraries(e500_ft_host PRIVATE "-framework CoreFoundation" "-framework IOKit")
endif()

add_executable(capture_ft_cpp
  src/capture_ft_main.cpp
)
target_link_libraries(capture_ft_cpp PRIVATE e500_ft_host)

add_executable(ft_to_vcd_cpp
  src/ft_to_vcd_main.cpp
)
target_link_libraries(ft_to_vcd_cpp PRIVATE e500_ft_host)
