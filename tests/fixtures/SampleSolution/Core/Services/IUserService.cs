using SampleSolution.Core.Models;

namespace SampleSolution.Core.Services;

public interface IUserService
{
    Task<User?> GetUserAsync(int id);
    Task<IEnumerable<User>> ListUsersAsync();
    Task CreateUserAsync(string name, string email);
}
