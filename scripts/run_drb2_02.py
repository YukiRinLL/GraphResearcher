from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_sampled_benchmark_job import main
import sys
sys.argv = [sys.argv[0], "--benchmark", "drb2", "--item", "11", *sys.argv[1:]]
main()
