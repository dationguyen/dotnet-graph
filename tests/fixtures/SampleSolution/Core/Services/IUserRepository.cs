using SampleSolution.Core.Models;

namespace SampleSolution.Core.Services;

public interface IUserRepository
{
    Task<User?> GetByIdAsync(int id);
    Task<IEnumerable<User>> GetAllAsync();
    Task SaveAsync(User user);
}
