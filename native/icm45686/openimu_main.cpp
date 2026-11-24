#include <exception>
#include <iostream>
#include <string>

int capture_openimu(int argc, char** argv);

int main(int argc, char** argv) {
  if (argc == 2 && std::string(argv[1]) == "--help") {
    std::cout << "capture-canfd IFACE SECONDS CSV\n"
              << "OpenIMU receive only: ID 1, FD+BRS, 16 big-endian bytes.\n"
              << "800Hz, +/-4g, +/-2000dps, X_DOWN_Z_BACK, 15s stationary bias.\n"
              << "No CAN transmission, motor access, or sensor configuration writes.\n";
    return 0;
  }
  try {
    if (argc != 5 || std::string(argv[1]) != "capture-canfd")
      throw std::runtime_error("see --help for capture-canfd arguments");
    return capture_openimu(argc, argv);
  } catch (const std::exception& e) {
    std::cerr << "OpenIMU capture failed: " << e.what() << '\n';
    return 1;
  }
}
