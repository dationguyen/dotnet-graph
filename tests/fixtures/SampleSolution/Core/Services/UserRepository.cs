using SampleSolution.Core.Models;

namespace SampleSolution.Core.Services;

public class UserRepository : IUserRepository
{
    private readonly List<User> _store = new();

    public async Task<User?> GetByIdAsync(int id)
    {
        await Task.CompletedTask;
        return _store.FirstOrDefault(u => u.Id == id);
    }

    public async Task<IEnumerable<User>> GetAllAsync()
    {
        await Task.CompletedTask;
        return _store.AsReadOnly();
    }

    public async Task SaveAsync(User user)
    {
        await Task.CompletedTask;
        _store.Add(user);
    }
}
