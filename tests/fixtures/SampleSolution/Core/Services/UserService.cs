using SampleSolution.Core.Models;

namespace SampleSolution.Core.Services;

public class UserService : IUserService
{
    private readonly IUserRepository _userRepository;

    public UserService(IUserRepository userRepository)
    {
        _userRepository = userRepository;
    }

    public async Task<User?> GetUserAsync(int id)
    {
        return await _userRepository.GetByIdAsync(id);
    }

    public async Task<IEnumerable<User>> ListUsersAsync()
    {
        return await _userRepository.GetAllAsync();
    }

    public async Task CreateUserAsync(string name, string email)
    {
        var user = new User { Name = name, Email = email, IsActive = true };
        await _userRepository.SaveAsync(user);
    }
}
